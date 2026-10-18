"""Bind retained explicit binary questions to exact Omen discovery evidence."""

import json
import re

from reputation_platform.prediction_evidence import EvidenceUnavailable, OMEN_INDEX

PREFIX = 'With the given question "'
SUFFIX = ('" and the `yes` option represented by `Yes` and the `no` option represented by `No`, '
          'what are the respective probabilities of `p_yes` and `p_no` occurring?')
METHOD = 'omen-exact-question-v1'


def extract_exact_question(original: dict) -> str:
    """Accept the observed complete Will/Yes/No template without normalization."""
    prompt = original.get('prompt') if isinstance(original, dict) else None
    if (not isinstance(prompt, str) or not prompt.startswith(PREFIX)
        or not prompt.endswith(SUFFIX) or prompt.count(SUFFIX) != 1):
        raise EvidenceUnavailable('Original request lacks the supported explicit binary-question template')
    title = prompt[len(PREFIX):-len(SUFFIX)]
    if not title.startswith('Will ') or not title.endswith('?'):
        raise EvidenceUnavailable('Original question is not the supported complete future-event question')
    return title


def _query(title: str) -> str:
    return ('{questions(first:2,where:{title:' + json.dumps(title, ensure_ascii=False)
            + '}){id title outcomes data indexedFixedProductMarketMakers(first:2){id}}}')


def _unique_question(questions, title: str) -> dict:
    if not isinstance(questions, list) or len(questions) != 1 or not isinstance(questions[0], dict):
        raise EvidenceUnavailable('Exact title has no unique indexed Omen question')
    question = questions[0]
    question_id, data = question.get('id'), question.get('data')
    if (not isinstance(question_id, str) or not re.fullmatch(r'0x[0-9a-f]{64}', question_id)
        or question.get('title') != title or question.get('outcomes') != ['Yes', 'No']
        or not isinstance(data, str)):
        raise EvidenceUnavailable('Exact indexed question does not preserve the original title and Yes/No options')
    parts = data.split('\u241f')
    try:
        options = json.loads('[' + parts[1] + ']') if len(parts) == 4 else None
    except json.JSONDecodeError as error:
        raise EvidenceUnavailable('Indexed question data does not encode the exact binary options') from error
    if len(parts) != 4 or parts[0] != title or options != ['Yes', 'No']:
        raise EvidenceUnavailable('Indexed question data differs from the original title and Yes/No options')
    markets = question.get('indexedFixedProductMarketMakers')
    if not isinstance(markets, list) or len(markets) != 1 or not isinstance(markets[0], dict):
        raise EvidenceUnavailable('Exact question does not have one unique indexed market')
    market = markets[0].get('id')
    if not isinstance(market, str) or not re.fullmatch(r'0x[0-9a-f]{40}', market):
        raise EvidenceUnavailable('Indexed market has no valid Gnosis contract address')
    return {'market': market, 'question_id': question_id, 'title': title, 'question_data': data}


def resolve_exact_question(store, original: dict) -> dict:
    """One official discovery query; settlement and correctness are not inferred."""
    title = extract_exact_question(original)
    index = store.graphql('omen-exact-question', OMEN_INDEX, _query(title))
    selected = _unique_question(index['data'].get('questions'), title)
    return {'method': METHOD, **selected, 'index': index}


def verify_exact_question_resolution(reader, resolution: dict, original: dict) -> str:
    """Rebuild the exact query and selection from retained observations and bytes."""
    try:
        title = extract_exact_question(original)
        if not isinstance(resolution, dict) or resolution.get('method') != METHOD:
            raise ValueError('Unsupported exact-question resolution method')
        index = resolution['index']
        observation, raw = reader.observation(index['evidence'], url=OMEN_INDEX, method='POST')
        request, response = json.loads(observation.request_json), json.loads(raw)
        if request != {'query': _query(title)}:
            raise ValueError('Original discovery query does not bind the exact title and both first:2 limits')
        if (not isinstance(response, dict) or response.get('errors')
            or not isinstance(response.get('data'), dict) or response['data'] != index.get('data')):
            raise ValueError('Copied exact-question discovery data differs from the original response')
        actual = _unique_question(response['data'].get('questions'), title)
        if any(resolution.get(key) != value for key, value in actual.items()):
            raise ValueError('Selected market or question differs from the original unique exact-title result')
        return actual['market']
    except (EvidenceUnavailable, KeyError, TypeError, json.JSONDecodeError) as error:
        raise ValueError('Exact-question resolution cannot be authenticated: ' + str(error)) from error
