"""Số hiệu extraction / flexible matching for QA direct lookup."""
from __future__ import annotations

from app.services.qa_service import QAService


def test_extract_so_hieu_without_year():
    q = "Nghị quyết 41/NQ-CP gồm những gì"
    assert QAService._extract_so_hieus(q) == ["41/NQ-CP"]
    assert QAService._SO_HIEU_RE.search(q)


def test_extract_so_hieu_with_year():
    q = "Theo 15/2020/NĐ-CP thì sao"
    got = QAService._extract_so_hieus(q)
    assert got == ["15/2020/ND-CP"]


def test_so_hieu_matches_year_optional():
    assert QAService._so_hieu_matches("41/NQ-CP", "41/NQ-CP")
    assert QAService._so_hieu_matches("41/2021/NQ-CP", "41/NQ-CP")
    assert QAService._so_hieu_matches("41/NQ-CP", "41/2021/NQ-CP")
    assert not QAService._so_hieu_matches("42/NQ-CP", "41/NQ-CP")
    assert not QAService._so_hieu_matches("41/ND-CP", "41/NQ-CP")


def test_doc_overview_detected():
    assert QAService._is_doc_overview_question("Nghị quyết 41/NQ-CP gồm những gì")
    assert QAService._is_doc_overview_question("Nội dung 15/2020/ND-CP")
    assert not QAService._is_doc_overview_question("mức phạt nồng độ cồn")
