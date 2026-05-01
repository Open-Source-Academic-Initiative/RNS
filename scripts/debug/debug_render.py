from starlette.requests import Request
from src.presentation.web import templates, DEFAULT_BUDGET, DEFAULT_MIN_BUDGET, DEFAULT_DEPARTMENT, DEFAULT_PROCESS_STATUS, DEFAULT_PHASE, DEFAULT_PROFILE, DEFAULT_PUBLISHED_SINCE_DAYS

scope = {'type': 'http', 'method': 'GET', 'path': '/', 'headers': [], 'query_string': b'', 'client': ('testclient', 50000), 'server': ('testserver', 80), 'scheme': 'http', 'root_path': ''}
request = Request(scope)
context = {
    'request': request,
    'results': None,
    'pagination': None,
    'min_budget': DEFAULT_MIN_BUDGET,
    'budget': DEFAULT_BUDGET,
    'department_sel': DEFAULT_DEPARTMENT,
    'process_status_sel': DEFAULT_PROCESS_STATUS,
    'phase_sel': DEFAULT_PHASE,
    'profile_sel': DEFAULT_PROFILE,
    'published_since_days': DEFAULT_PUBLISHED_SINCE_DAYS,
    'keyword': '',
    'sort_by': 'match_score',
    'sort_dir': 'desc',
    'only_high_fit': True,
    'only_new': False,
    'departments': [],
    'process_statuses': [],
    'phases': [],
    'profiles': [],
    'published_windows': [],
    'error': None,
}
print('before', flush=True)
html = templates.get_template('index.html').render(context)
print('after', len(html), flush=True)
