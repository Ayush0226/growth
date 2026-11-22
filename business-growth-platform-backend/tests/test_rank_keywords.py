import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from pydantic import ValidationError

from app.routes import google


def test_keyword_priorities_preserve_order_and_normalize_spaces():
    data = google.RankKeywordsInput(keywords=['  preschool   near me ', 'daycare', 'nursery'])
    assert data.keywords == ['preschool near me', 'daycare', 'nursery']


@pytest.mark.parametrize('words', [['x']*11, ['Cafe', ' cafe '], ['   '], ['a'*121]])
def test_keywords_reject_over_limit_duplicates_and_blank_phrases(words):
    with pytest.raises(ValidationError):
        google.RankKeywordsInput(keywords=words)


def test_all_keywords_can_be_removed():
    assert google.RankKeywordsInput(keywords=[]).keywords == []


def test_saving_keywords_requires_owned_location_before_any_write(monkeypatch):
    from fastapi import HTTPException
    monkeypatch.setattr(google, 'context', AsyncMock(side_effect=HTTPException(403)))
    execute = AsyncMock()
    monkeypatch.setattr(google.service, 'execute', execute)
    with pytest.raises(HTTPException):
        asyncio.run(google.save_rank_keywords(google.RankKeywordsInput(location_name='accounts/a/locations/l', keywords=['daycare']), SimpleNamespace(id='other'), SimpleNamespace()))
    execute.assert_not_called()


def test_failed_scan_keeps_last_successful_measurement(monkeypatch):
    query = SimpleNamespace()
    for method in ('select','eq','in_','order','limit'):
        setattr(query, method, lambda *a, **k: query)
    monkeypatch.setattr(google,'db',lambda: SimpleNamespace(table=lambda name:query))
    monkeypatch.setattr(google.service,'execute',AsyncMock(return_value=[
        {'id':'new','keyword':'daycare','status':'failed','created_at':'2026-11-22T00:00:00Z','report':None},
        {'id':'old','keyword':'daycare','status':'completed','created_at':'2026-11-21T00:00:00Z','report':{'results':[], 'actual_rank':None}},
    ]))
    state=asyncio.run(google.rank_keyword_state('workspace','accounts/a/locations/l',['daycare']))
    assert state['reports'][0]['id']=='old'
    assert state['reports'][0]['latest_attempt_status']=='failed'


def test_blank_single_keyword_is_rejected():
    with pytest.raises(ValidationError):
        google.RankInput(keyword='   ', request_id='00000000-0000-4000-8000-000000000001')
