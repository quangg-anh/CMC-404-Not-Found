import assert from 'node:assert/strict';
import test from 'node:test';

import { formatLegalCoordinate, normalizeQAResponse } from '../apps/web/src/lib/qaContract.ts';

test('normalizes an answered Citation Contract v2 without trusting legacy aliases', () => {
  const response = normalizeQAResponse({
    status: 'answered',
    as_of: '2026-07-01',
    answer: 'Ngưỡng áp dụng là 500 triệu đồng.',
    claims: [{
      claim_id: 'claim_1',
      text: 'Ngưỡng áp dụng là 500 triệu đồng.',
      citation_ids: ['citation_1'],
      support_status: 'entailed',
    }],
    citations: [{
      citation_id: 'citation_1',
      node_id: '01/2026/ND-CP::D5.K2.Pa@2026-07-01#abc',
      lineage_id: '01/2026/ND-CP::D5.K2.Pa',
      level: 'diem',
      document_number: '01/2026/NĐ-CP',
      article: '5',
      clause: '2',
      point: 'a',
      quote: 'Ngưỡng áp dụng là 500 triệu đồng.',
      effective_from: '2026-07-01',
      effective_to: null,
      supports_claim_ids: ['claim_1'],
      entailment_score: 0.97,
      validation_source: 'neo4j',
    }],
  });

  assert.equal(response.contractVersion, 'v2');
  assert.equal(response.status, 'answered');
  assert.equal(response.confidence, 'high');
  assert.equal(response.citations[0]?.supportStatus, 'entailed');
  assert.equal(response.citations[0]?.validationSource, 'neo4j');
  assert.equal(formatLegalCoordinate(response.citations[0]!), 'Điều 5, Khoản 2, Điểm a');
});

test('turns a refused v2 response into a safe, readable UI state', () => {
  const response = normalizeQAResponse({
    status: 'refused',
    as_of: '2026-07-01',
    answer: null,
    claims: [],
    citations: [],
    reason_code: 'insufficient_legal_basis',
  });

  assert.equal(response.refused, true);
  assert.equal(response.unverified, true);
  assert.equal(response.citations.length, 0);
  assert.match(response.answer, /Chưa tìm thấy đủ căn cứ pháp lý/);
});

test('keeps a legacy v1 response readable during rollout', () => {
  const response = normalizeQAResponse({
    answer: 'Câu trả lời v1.',
    confidence: 'medium',
    citations: [{
      khoan_id: '15/2020/ND-CP::D5.K2',
      van_ban: 'Nghị định 15/2020/NĐ-CP',
      dieu: 'Điều 5',
      quote: 'Nội dung khoản 2.',
    }],
    graph_paths: [{ nodes: [] }],
    cached: true,
  }, '2026-07-01');

  assert.equal(response.contractVersion, 'v1');
  assert.equal(response.answer, 'Câu trả lời v1.');
  assert.equal(response.citations[0]?.khoanId, '15/2020/ND-CP::D5.K2');
  assert.equal(response.citations[0]?.clause, '2');
  assert.equal(response.graphPaths.length, 1);
  assert.equal(response.cached, true);
});
