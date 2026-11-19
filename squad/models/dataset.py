"""Synthetic data generation for the TF classifier scaffold.

These generators produce small, deterministic example sets so the pipeline runs
out-of-the-box. Replace them with real loaders (CSV/JSONL) when you have data.
"""

from __future__ import annotations

import random

# --- Intent classifier ------------------------------------------------------
# (example, label) pairs modelled loosely on squad/chat/offline intents.
# Enriched with varied natural phrasing so the offline classifier generalizes.
_INTENT_EXAMPLES: list[tuple[str, str]] = [
    # review
    ("review C:/code/app.py", "review"),
    ("audit code utils.py", "review"),
    ("scan code auth.py", "review"),
    ("check code for security", "review"),
    ("review this file for bugs", "review"),
    ("audit my project for vulnerabilities", "review"),
    ("can you review this file", "review"),
    ("look over my code for issues", "review"),
    ("please audit app.py for me", "review"),
    ("do a code review on main.py", "review"),
    ("check my code quality", "review"),
    ("scan the code for bugs", "review"),
    ("inspect this script", "review"),
    ("run a review on this module", "review"),
    ("find problems in my code", "review"),
    ("review the changes in this repo", "review"),
    # testgen
    ("generate tests for db.py", "testgen"),
    ("write tests for api.py", "testgen"),
    ("make tests for utils.py", "testgen"),
    ("create unit tests for this module", "testgen"),
    ("add tests for the parser", "testgen"),
    ("write unit tests please", "testgen"),
    ("generate a test suite", "testgen"),
    ("i need tests for auth.py", "testgen"),
    ("create test cases for this code", "testgen"),
    ("build tests for the handler", "testgen"),
    ("produce tests for models.py", "testgen"),
    ("draft tests for this file", "testgen"),
    ("make me tests for the service", "testgen"),
    ("write pytest for app.py", "testgen"),
    # refactor
    ("refactor legacy.py", "refactor"),
    ("modernize auth.py", "refactor"),
    ("clean up this old code", "refactor"),
    ("improve this code structure", "refactor"),
    ("refactor the login module", "refactor"),
    ("simplify this function", "refactor"),
    ("clean up the controller", "refactor"),
    ("improve the performance of utils", "refactor"),
    ("restructure this class", "refactor"),
    ("make this code more readable", "refactor"),
    ("split this file into modules", "refactor"),
    ("remove duplication in this repo", "refactor"),
    ("tidy up this codebase", "refactor"),
    ("optimize the database code", "refactor"),
    # scan
    ("scan 127.0.0.1", "scan"),
    ("pentest example.com", "scan"),
    ("run nightwing against 10.0.0.4", "scan"),
    ("do a security scan on my server", "scan"),
    ("test the website for vulnerabilities", "scan"),
    ("scan my api endpoint", "scan"),
    ("run a port scan on this host", "scan"),
    ("attack surface scan example.com", "scan"),
    ("recon on 192.168.1.1", "scan"),
    ("check the website for open ports", "scan"),
    ("nightwing scan this url", "scan"),
    ("probe the target for weaknesses", "scan"),
    ("scan the server now", "scan"),
    ("run the scanner on my domain", "scan"),
    ("enum the services on this host", "scan"),
    # fetch
    ("fetch intel", "fetch"),
    ("update feed", "fetch"),
    ("refresh the intel feeds", "fetch"),
    ("pull the latest advisories", "fetch"),
    ("update threat intel", "fetch"),
    ("fetch new security data", "fetch"),
    ("refresh my intel feed", "fetch"),
    ("download the latest intel", "fetch"),
    ("sync the vulnerability feed", "fetch"),
    ("update the intel database", "fetch"),
    # search
    ("search cve-2021-44228", "search"),
    ("search sql injection", "search"),
    ("search for log4shell advisory", "search"),
    ("find intel on cve-2023-1234", "search"),
    ("look up cross-site scripting", "search"),
    ("search the feed for rce", "search"),
    ("get info about this cve", "search"),
    ("search advisories for jwt", "search"),
    ("find anything about zero-day", "search"),
    ("look up the latest vuln", "search"),
    # status
    ("security status", "status"),
    ("scan status", "status"),
    ("how many scans have run", "status"),
    ("what is the current status", "status"),
    ("show me my scan history", "status"),
    ("any scans running", "status"),
    ("report the status", "status"),
    ("how are my security checks doing", "status"),
    # doctor
    ("doctor", "doctor"),
    ("run self check", "doctor"),
    ("health check my environment", "doctor"),
    ("diagnose my setup", "doctor"),
    ("are my tools working", "doctor"),
    ("run the doctor", "doctor"),
    ("check my environment health", "doctor"),
    ("verify my install", "doctor"),
    ("run a diagnostic", "doctor"),
    # tools
    ("check tools", "tools"),
    ("which security tools are installed", "tools"),
    ("list installed pentest tools", "tools"),
    ("show me my tools", "tools"),
    ("what tools do i have", "tools"),
    ("check tool availability", "tools"),
    ("list my available tools", "tools"),
    # export
    ("export run-12 as csv", "export"),
    ("dump the findings to a report", "export"),
    ("export the last scan to csv", "export"),
    ("save results to a file", "export"),
    ("export history as csv", "export"),
    ("download my scan report", "export"),
    ("write the findings to csv", "export"),
    # llm
    ("what is sql injection", "llm"),
    ("explain tls handshake", "llm"),
    ("recommend how to harden an API", "llm"),
    ("write code for a login endpoint", "llm"),
    ("explain xss to me", "llm"),
    ("how does oauth work", "llm"),
    ("teach me about reverse shells", "llm"),
    ("explain buffer overflow", "llm"),
    ("best practices for password hashing", "llm"),
    ("what is a man in the middle attack", "llm"),
    ("explain public key cryptography", "llm"),
    ("how do i secure a database", "llm"),
    # interactive
    ("add target 10.0.0.5", "interactive"),
    ("authorize a new target", "interactive"),
    ("register my server for scanning", "interactive"),
    ("add example.com to my scope", "interactive"),
    ("add this host to the list", "interactive"),
    ("set up a new target", "interactive"),
    ("add my staging server", "interactive"),
]


def _augment(text: str, rng: random.Random) -> str:
    """Vary phrasing (politeness, hedging, intent markers) for robustness."""
    r = rng.random()
    if r < 0.25:
        return "please " + text
    if r < 0.35:
        return "hey, " + text
    if r < 0.45:
        return "can you " + text
    if r < 0.55:
        return "i want to " + text
    if r < 0.65:
        return text + " please"
    return text


def intent_dataset(n_per_class: int = 16, seed: int = 7):
    """Return (texts, labels) with n_per_class variants per intent."""
    rng = random.Random(seed)
    texts: list[str] = []
    labels: list[str] = []
    by_label: dict[str, list[str]] = {}
    for t, lab in _INTENT_EXAMPLES:
        by_label.setdefault(lab, []).append(t)
    for lab, examples in by_label.items():
        for _ in range(n_per_class):
            base = rng.choice(examples)
            texts.append(_augment(base, rng))
            labels.append(lab)
    return texts, labels, sorted(by_label.keys())


# --- Code-security classifier ----------------------------------------------
# Rough vulnerable vs safe snippets. This is illustrative, not a real vuln set.
_SECURITY_EXAMPLES: list[tuple[str, int]] = [
    # Vulnerable (label 1)
    ("SELECT * FROM users WHERE name = '" + user_input + "'", 1)
    for user_input in ["user", "name", "term", "input", "data"]
] + [
    ("sql = \"SELECT * FROM t WHERE id=\" + request.args['id']", 1),
    ("password = request.form['pw']", 1),  # passed as marker for missing validation
    ("eval(request.args.get('code'))", 1),
    ("exec(user_input)", 1),
    ("os.system('rm -rf /' + user_input)", 1),
    ('conn.execute("SELECT * FROM t WHERE id=" + user_id)', 1),
    ("pickle.loads(untrusted_bytes)", 1),
    ("render_template_string(user_html)", 1),
    ("subprocess.call('curl ' + url, shell=True)", 1),
    ('query = f"SELECT * FROM users WHERE id={uid}"', 1),
    ("cmd = 'ping ' + host; os.system(cmd)", 1),
    ('html = f"<div>{user_comment}</div>"; return html', 1),
    ("conn.execute('DELETE FROM t WHERE id=' + str(req_id))", 1),
    ("hash = md5(password).hexdigest()", 1),
    ("loads(request.data)", 1),
    ("open('file', 'w').write(untrusted)", 1),
    ("redirect(request.referrer)", 1),
    # Safe (label 0)
    ("query = 'SELECT * FROM users WHERE id = ?'; execute(query, (uid,))", 0),
    ("conn = sqlite3.connect(db); cur.execute('SELECT * FROM t WHERE id = ?', (i,))", 0),
    ("password = request.form['pw']; check_password_hash(user.pw, password)", 0),
    ("allow = True", 0),
    ("query = select().where(User.name == name); db.execute(query)", 0),
    ("with open(path, 'r') as f: data = f.read()", 0),
    ("subprocess.run(['ls', '-la'], check=True)", 0),
    ("result = bcrypt.hashpw(pw.encode(), bcrypt.gensalt())", 0),
    ("cur.execute('INSERT INTO t VALUES (?)', (val,))", 0),
    ("esc = html.escape(user_input)", 0),
    ("token = secrets.token_urlsafe(32)", 0),
    ("hashed = argon2.hash(password)", 0),
    ("cur.execute('SELECT * FROM t WHERE id = ?', [uid])", 0),
    ("if re.fullmatch(r'[0-9]+', uid): do_work(uid)", 0),
    ("safe = bleach.clean(user_html)", 0),
    ("result = hmac.compare_digest(a, b)", 0),
    ("render_template('page.html', name=name)", 0),
    ("session.secure = True", 0),
]


def security_dataset(n_per_class: int = 18, seed: int = 11):
    """Return (texts, labels) of code snippets; label 1 = vulnerable."""
    random.Random(seed)
    texts: list[str] = []
    labels: list[int] = []
    for snip, lab in _SECURITY_EXAMPLES:
        for _ in range(n_per_class):
            texts.append(snip)
            labels.append(lab)
    return texts, labels
