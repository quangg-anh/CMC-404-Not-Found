export type Confidence = 'high' | 'medium' | 'low';
export type ContractVersion = 'v1' | 'v2';
export type ClaimSupportStatus = 'entailed' | 'unsupported' | 'needs_review';
export type ProvisionLevel = 'dieu' | 'khoan' | 'diem';

export interface NormalizedClaim {
  claimId: string;
  text: string;
  citationIds: string[];
  supportStatus: ClaimSupportStatus;
}

export interface NormalizedCitation {
  citationId?: string;
  nodeId?: string;
  lineageId?: string;
  level?: ProvisionLevel;
  documentNumber: string;
  article: string;
  clause?: string;
  point?: string;
  quote?: string;
  effectiveFrom?: string;
  effectiveTo?: string;
  asOf?: string;
  supportsClaimIds: string[];
  supportStatus?: ClaimSupportStatus;
  entailmentScore?: number;
  validationSource?: 'neo4j';
  /** Compatibility alias kept while the v1 API is still supported. */
  khoanId?: string;
}

export interface NormalizedQAResponse {
  contractVersion: ContractVersion;
  status: 'answered' | 'refused';
  answer: string;
  citations: NormalizedCitation[];
  claims: NormalizedClaim[];
  graphPaths: unknown[];
  confidence: Confidence;
  refused: boolean;
  reasonCode?: string;
  refusalMessage?: string;
  refuseReasons: string[];
  asOf?: string;
  notices: unknown[];
  unverified: boolean;
  degraded: boolean;
  cached: boolean;
}

type UnknownRecord = Record<string, unknown>;

const REFUSAL_MESSAGES: Record<string, string> = {
  canonical_validator_unavailable: 'Hệ thống kiểm tra căn cứ pháp lý đang tạm thời không khả dụng.',
  citation_v2_dependencies_disabled: 'Chế độ kiểm chứng pháp luật theo thời điểm chưa được kích hoạt đầy đủ.',
  citation_v2_service_unavailable: 'Dịch vụ hỏi đáp pháp lý đã xác thực đang tạm thời không khả dụng.',
  insufficient_legal_basis: 'Chưa tìm thấy đủ căn cứ pháp lý đã xác thực để trả lời câu hỏi này.',
  invalid_as_of: 'Ngày áp dụng không hợp lệ. Vui lòng chọn lại ngày cần tra cứu.',
  invalid_model_output: 'Câu trả lời dự kiến không vượt qua kiểm tra cấu trúc và đã bị từ chối.',
  legal_retrieval_unavailable: 'Kho dữ liệu pháp lý đang tạm thời không khả dụng.',
  llm_generation_unavailable: 'Hệ thống chưa thể tạo câu trả lời đã kiểm chứng vào lúc này.',
  llm_router_unavailable: 'Mô-đun tổng hợp câu trả lời đang tạm thời không khả dụng.',
  non_legal_meta_question: 'Câu hỏi này nằm ngoài phạm vi tra cứu pháp luật của hệ thống.',
};

function isRecord(value: unknown): value is UnknownRecord {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

function asString(value: unknown): string | undefined {
  return typeof value === 'string' && value.trim() ? value.trim() : undefined;
}

function asStringArray(value: unknown): string[] {
  return Array.isArray(value)
    ? value.map(asString).filter((item): item is string => Boolean(item))
    : [];
}

function asRecordArray(value: unknown): UnknownRecord[] {
  return Array.isArray(value) ? value.filter(isRecord) : [];
}

function normalizeSupportStatus(value: unknown): ClaimSupportStatus | undefined {
  return value === 'entailed' || value === 'unsupported' || value === 'needs_review'
    ? value
    : undefined;
}

function normalizeLevel(value: unknown): ProvisionLevel | undefined {
  return value === 'dieu' || value === 'khoan' || value === 'diem' ? value : undefined;
}

function coordinateFromLegacy(citation: UnknownRecord): {
  article: string;
  clause?: string;
  point?: string;
} {
  const id = asString(citation.node_id) ?? asString(citation.khoan_id) ?? '';
  const article =
    asString(citation.article) ??
    asString(citation.dieu)?.match(/\d+[a-zđ]?/iu)?.[0] ??
    id.match(/::D([^.@#]+)/iu)?.[1] ??
    '';
  const clause = asString(citation.clause) ?? id.match(/\.K([^.@#]+)/iu)?.[1];
  const point = asString(citation.point) ?? id.match(/\.P([^.@#]+)/iu)?.[1];
  return { article, clause, point };
}

function normalizeCitation(
  citation: UnknownRecord,
  claimStatusByCitation: Map<string, ClaimSupportStatus>,
  asOf?: string,
): NormalizedCitation {
  const citationId = asString(citation.citation_id);
  const nodeId = asString(citation.node_id);
  const legacyId = asString(citation.khoan_id);
  const coordinates = coordinateFromLegacy(citation);
  const validationSource = citation.validation_source === 'neo4j' ? 'neo4j' : undefined;
  const score = typeof citation.entailment_score === 'number'
    ? citation.entailment_score
    : typeof citation.score === 'number'
      ? citation.score
      : undefined;

  return {
    citationId,
    nodeId,
    lineageId: asString(citation.lineage_id),
    level: normalizeLevel(citation.level),
    documentNumber:
      asString(citation.document_number) ??
      asString(citation.van_ban) ??
      (nodeId ?? legacyId ?? '').split('::')[0] ??
      'Văn bản chưa xác định',
    article: coordinates.article,
    clause: coordinates.clause,
    point: coordinates.point,
    quote: asString(citation.quote),
    effectiveFrom: asString(citation.effective_from),
    effectiveTo: asString(citation.effective_to),
    asOf,
    supportsClaimIds: asStringArray(citation.supports_claim_ids),
    supportStatus: citationId ? claimStatusByCitation.get(citationId) : undefined,
    entailmentScore: score,
    validationSource,
    khoanId: legacyId ?? nodeId,
  };
}

function normalizeClaims(payload: UnknownRecord): NormalizedClaim[] {
  return asRecordArray(payload.claims).flatMap((claim) => {
    const claimId = asString(claim.claim_id);
    const text = asString(claim.text);
    const supportStatus = normalizeSupportStatus(claim.support_status);
    if (!claimId || !text || !supportStatus) return [];
    return [{
      claimId,
      text,
      citationIds: asStringArray(claim.citation_ids),
      supportStatus,
    }];
  });
}

function refusalMessage(reasonCode?: string): string {
  if (!reasonCode) return 'Hệ thống chưa thể trả lời vì không có đủ căn cứ pháp lý đã xác thực.';
  return REFUSAL_MESSAGES[reasonCode] ?? 'Câu trả lời không vượt qua kiểm tra căn cứ pháp lý và đã được từ chối.';
}

export function normalizeQAResponse(payload: unknown, fallbackAsOf?: string): NormalizedQAResponse {
  const data = isRecord(payload) ? payload : {};
  const isV2 = data.status === 'answered' || data.status === 'refused';
  const asOf = asString(data.as_of) ?? fallbackAsOf;

  if (isV2) {
    const status = data.status as 'answered' | 'refused';
    const reasonCode = asString(data.reason_code);
    const claims = normalizeClaims(data);
    const claimStatusByCitation = new Map<string, ClaimSupportStatus>();
    for (const claim of claims) {
      for (const citationId of claim.citationIds) {
        const current = claimStatusByCitation.get(citationId);
        claimStatusByCitation.set(
          citationId,
          current === 'unsupported' || claim.supportStatus === 'unsupported'
            ? 'unsupported'
            : current === 'needs_review' || claim.supportStatus === 'needs_review'
              ? 'needs_review'
              : 'entailed',
        );
      }
    }
    const refused = status === 'refused';
    return {
      contractVersion: 'v2',
      status,
      answer: refused ? refusalMessage(reasonCode) : asString(data.answer) ?? '',
      citations: asRecordArray(data.citations).map((citation) =>
        normalizeCitation(citation, claimStatusByCitation, asOf),
      ),
      claims,
      graphPaths: [],
      confidence: refused ? 'low' : 'high',
      refused,
      reasonCode,
      refusalMessage: refused ? refusalMessage(reasonCode) : undefined,
      refuseReasons: reasonCode ? [reasonCode] : [],
      asOf,
      notices: [],
      unverified: refused,
      degraded: false,
      cached: false,
    };
  }

  const refused = data.refused === true;
  const refuseReasons = asStringArray(data.refuse_reason);
  const claimStatusByCitation = new Map<string, ClaimSupportStatus>();
  const confidence = data.confidence === 'high' || data.confidence === 'medium' || data.confidence === 'low'
    ? data.confidence
    : 'low';
  return {
    contractVersion: 'v1',
    status: refused ? 'refused' : 'answered',
    answer: asString(data.answer) ?? (refused ? refusalMessage() : ''),
    citations: asRecordArray(data.citations).map((citation) =>
      normalizeCitation(citation, claimStatusByCitation, asOf),
    ),
    claims: [],
    graphPaths: Array.isArray(data.graph_paths) ? data.graph_paths : [],
    confidence,
    refused,
    refuseReasons,
    asOf,
    notices: Array.isArray(data.notices) ? data.notices : [],
    unverified: data.unverified === true,
    degraded: data.degraded === true,
    cached: data.cached === true,
  };
}

export function formatLegalCoordinate(citation: NormalizedCitation): string {
  const parts = citation.article ? [`Điều ${citation.article}`] : [];
  if (citation.clause) parts.push(`Khoản ${citation.clause}`);
  if (citation.point) parts.push(`Điểm ${citation.point}`);
  return parts.join(', ') || 'Chưa xác định điều khoản';
}
