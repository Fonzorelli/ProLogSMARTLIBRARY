
"""ProLogSMARTLIBRARY - COSC 430 (Python + SQLite + SWI-Prolog)."""

import re
import sqlite3
import subprocess
import tempfile
from datetime import date, timedelta
from pathlib import Path

from community import (
    register,
    rate,
    save_bookmark,
    bookmarks,
    reminders
)

ROOT = Path(__file__).resolve().parent
DB = ROOT / "library.db"


# ==========================================
# DATABASE CONNECTION
# ==========================================

def connect():
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    return conn


def initialize(db):
    """Create tables and update the existing database."""

    db.executescript("""
        CREATE TABLE IF NOT EXISTS students (
            student_id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            age INTEGER,
            email TEXT UNIQUE,
            phone TEXT,
            favorite_genre TEXT,
            active INTEGER DEFAULT 1,
            reminders INTEGER DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS books (
            book_id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            author TEXT NOT NULL,
            genre TEXT NOT NULL,
            pages INTEGER NOT NULL,
            keywords TEXT,
            copies INTEGER DEFAULT 1
        );

        CREATE TABLE IF NOT EXISTS borrowed_books (
            student_id INTEGER,
            book_id INTEGER,
            borrow_date TEXT,
            due_date TEXT,
            returned INTEGER DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS ratings (
            student_id INTEGER,
            book_id INTEGER,
            rating INTEGER CHECK(rating BETWEEN 1 AND 5),
            PRIMARY KEY(student_id, book_id)
        );

        CREATE TABLE IF NOT EXISTS bookmarks (
            student_id INTEGER,
            book_id INTEGER,
            current_page INTEGER DEFAULT 0,
            PRIMARY KEY(student_id, book_id)
        );

        CREATE TABLE IF NOT EXISTS requests (
            student_id INTEGER,
            book_id INTEGER,
            UNIQUE(student_id, book_id)
        );

        CREATE TABLE IF NOT EXISTS prolog_rules (
            rule_id INTEGER PRIMARY KEY AUTOINCREMENT,
            rule_name TEXT UNIQUE,
            rule_code TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS stored_code (
            filename TEXT PRIMARY KEY,
            source_code TEXT NOT NULL
        );
    """)

    # Update older databases without deleting records.
    columns = {
        row["name"]
        for row in db.execute(
            "PRAGMA table_info(students)"
        )
    }

    if "active" not in columns:
        db.execute("""
            ALTER TABLE students
            ADD COLUMN active INTEGER DEFAULT 1
        """)

    if "reminders" not in columns:
        db.execute("""
            ALTER TABLE students
            ADD COLUMN reminders INTEGER DEFAULT 0
        """)

    # Save Python and Prolog source code in SQLite.
    files = [
        "rules.pl",
        "community_rules.pl",
        "main.py",
        "community.py",
        "generate_books.py"
    ]

    for filename in files:
        path = ROOT / filename

        if not path.exists():
            print(
                f"Library: Warning: {filename} is missing."
            )
            continue

        source = path.read_text(encoding="utf-8")

        db.execute("""
            INSERT INTO stored_code(
                filename, source_code
            )
            VALUES (?, ?)
            ON CONFLICT(filename)
            DO UPDATE SET
                source_code = excluded.source_code
        """, (filename, source))

        if filename.endswith(".pl"):
            db.execute("""
                INSERT INTO prolog_rules(
                    rule_name, rule_code
                )
                VALUES (?, ?)
                ON CONFLICT(rule_name)
                DO UPDATE SET
                    rule_code = excluded.rule_code
            """, (filename, source))

    # Add a fictional test student if needed.
    alex = db.execute("""
        SELECT 1
        FROM students
        WHERE name = ? COLLATE NOCASE
    """, ("Alex",)).fetchone()

    if alex is None:
        db.execute("""
            INSERT INTO students(
                name, age, email, favorite_genre
            )
            VALUES (?, ?, ?, ?)
        """, (
            "Alex",
            21,
            "alex@example.com",
            "Science Fiction"
        ))

    db.commit()


# ==========================================
# LOOK UP STUDENTS AND BOOKS
# ==========================================

def student(db, name):
    return db.execute("""
        SELECT *
        FROM students
        WHERE name = ? COLLATE NOCASE
    """, (name.strip(),)).fetchone()


def book(db, title):
    return db.execute("""
        SELECT *
        FROM books
        WHERE title = ? COLLATE NOCASE
    """, (title.strip(),)).fetchone()


# ==========================================
# PROLOG CONNECTION
# ==========================================

def prolog_atom(value):
    """Convert Python text to a quoted Prolog atom."""

    text = str(value)

    text = text.replace("\\", "\\\\")
    text = text.replace("'", "''")
    text = text.replace("\n", " ")
    text = text.replace("\r", " ")

    return "'" + text + "'"


def make_facts(db):
    """Turn SQL data into Prolog facts."""

    facts = []

    # Student facts
    for s in db.execute("SELECT * FROM students"):
        sid = s["student_id"]

        status = (
            "active"
            if s["active"]
            else "inactive"
        )

        facts.append(
            f"student({sid}, {status})."
        )

        count = db.execute("""
            SELECT COUNT(*)
            FROM borrowed_books
            WHERE student_id = ?
              AND returned = 0
        """, (sid,)).fetchone()[0]

        facts.append(
            f"loan_count({sid}, {count})."
        )

        if s["favorite_genre"]:
            genre = prolog_atom(
                s["favorite_genre"].lower()
            )

            facts.append(
                f"favorite_genre({sid}, {genre})."
            )

    # Book facts
    for b in db.execute("SELECT * FROM books"):
        bid = b["book_id"]

        copies = b["copies"] or 0

        facts.append(
            f"book({bid}, {copies})."
        )

        author = prolog_atom(
            b["author"].lower()
        )

        genre = prolog_atom(
            b["genre"].lower()
        )

        facts.append(
            f"book_author({bid}, {author})."
        )

        facts.append(
            f"book_genre({bid}, {genre})."
        )

        facts.append(
            f"book_pages({bid}, {b['pages']})."
        )

        keywords = (
            b["keywords"] or ""
        ).lower()

        words = set(
            re.findall(r"[a-z0-9]+", keywords)
        )

        for word in words:
            facts.append(
                f"keyword({bid}, {prolog_atom(word)})."
            )

    # Existing loans
    loans = db.execute("""
        SELECT student_id, book_id
        FROM borrowed_books
        WHERE returned = 0
    """)

    for loan in loans:
        facts.append(
            f"loan({loan[0]}, {loan[1]})."
        )

    # Student ratings
    ratings_data = db.execute("""
        SELECT student_id, book_id, rating
        FROM ratings
    """)

    for rating in ratings_data:
        facts.append(
            f"rated({rating[0]}, "
            f"{rating[1]}, {rating[2]})."
        )

    return "\n".join(facts) + "\n"


def prolog(db, goal):
    """Ask SWI-Prolog a question using SQL data."""

    # Load only the two current Prolog rule files.
    rules = db.execute("""
        SELECT rule_name, rule_code
        FROM prolog_rules
        WHERE rule_name IN (
            'rules.pl',
            'community_rules.pl'
        )
        ORDER BY rule_name
    """).fetchall()

    if len(rules) != 2:
        print(
            "Library: Save rules.pl and "
            "community_rules.pl first."
        )
        return None

    source = "\n".join(
        row["rule_code"]
        for row in rules
    )

    source += "\n" + make_facts(db)

    try:
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "knowledge.pl"

            path.write_text(
                source,
                encoding="utf-8"
            )

            result = subprocess.run(
                [
                    "swipl",
                    "-q",
                    "-s", str(path),
                    "-g", goal,
                    "-t", "halt"
                ],
                capture_output=True,
                text=True,
                timeout=15
            )

    except (
        FileNotFoundError,
        subprocess.TimeoutExpired
    ) as error:

        print(
            f"Library: Could not start Prolog: {error}"
        )
        return None

    if result.returncode != 0:
        print("Library: Prolog error:")
        print(result.stderr.strip())
        return None

    return result.stdout.strip()


# ==========================================
# BOOK SEARCH
# ==========================================

def search_books(db, question):
    """Search books by genre, author, keywords, or pages."""

    text = question.lower()

    # Recognize different spellings of science fiction.
    text = re.sub(
        r"\b(sy\s*fy|sci[ -]?fi|scifi)\b",
        "science fiction",
        text
    )

    genres = [
        "science fiction",
        "young adult",
        "mystery",
        "fantasy",
        "romance",
        "horror",
        "history",
        "technology",
        "adventure",
        "sports"
    ]

    genre = next(
        (g for g in genres if g in text),
        None
    )

    short = re.search(
        r"(?:under|less than)\s+(\d+)\s+pages",
        text
    )

    long = re.search(
        r"(?:over|more than)\s+(\d+)\s+pages",
        text
    )

    clauses = []
    params = []

    if genre:
        clauses.append("LOWER(genre) = ?")
        params.append(genre)

    else:
        query = re.sub(
            r"^(?:show me|find me|find|search for|"
            r"search|look for|do you have|got any|"
            r"i want|i'd like)\s+",
            "",
            text
        )

        query = re.sub(
            r"\b(books?|novels?|some|any|about|"
            r"by|please|the|a|an|of|with)\b",
            " ",
            query
        )

        query = re.sub(
            r"(?:under|less than|over|more than)"
            r"\s+\d+\s+pages",
            " ",
            query
        )

        words = re.findall(
            r"[a-z0-9]+",
            query
        )

        if words:
            pieces = []

            for word in words:
                pieces.append("""
                    (
                        LOWER(title) LIKE ?
                        OR LOWER(author) LIKE ?
                        OR LOWER(keywords) LIKE ?
                    )
                """)

                params.extend(
                    [f"%{word}%"] * 3
                )

            clauses.append(
                "(" + " OR ".join(pieces) + ")"
            )

    if short:
        clauses.append("pages < ?")
        params.append(int(short.group(1)))

    if long:
        clauses.append("pages > ?")
        params.append(int(long.group(1)))

    sql = "SELECT * FROM books"

    if clauses:
        sql += " WHERE " + " AND ".join(clauses)

    sql += " ORDER BY title LIMIT 10"

    rows = db.execute(sql, params).fetchall()

    if not rows:
        print(
            "Library: I couldn't find matching books."
        )
        return

    print("\nLibrary: Here's what I found:\n")

    for b in rows:
        print(f"  {b['title']}")
        print(f"  Author: {b['author']}")
        print(f"  Genre: {b['genre']}")
        print(f"  Pages: {b['pages']}")
        print(
            f"  Available copies: {b['copies']}\n"
        )


# ==========================================
# CHECK BOOK AVAILABILITY
# ==========================================

def availability(db, title):

    found = book(db, title)

    if found is None:
        print(
            f"Library: I couldn't find a book "
            f"called {title}."
        )
        return

    if found["copies"] > 0:
        print(
            f"Library: Yes! {found['title']} "
            f"has {found['copies']} copies available."
        )

    else:
        print(
            f"Library: {found['title']} is "
            "currently unavailable (0 copies)."
        )


# ==========================================
# BORROWING ELIGIBILITY
# ==========================================

def eligibility(db, name, title, checkout=False):
    """Use Prolog to decide whether borrowing is allowed."""

    s = student(db, name)
    b = book(db, title)

    if s is None or b is None:
        message = (
            "the student or book could not be found."
        )

        print("Library: Sorry, " + message)
        return message

    sid = s["student_id"]
    bid = b["book_id"]

    goal = (
        f"(can_borrow({sid}, {bid}) "
        "-> writeln(yes) ; writeln(no))"
    )

    answer = prolog(db, goal)

    if answer is None:
        return (
            "Prolog could not complete "
            "the eligibility check."
        )

    count = db.execute("""
        SELECT COUNT(*)
        FROM borrowed_books
        WHERE student_id = ?
          AND returned = 0
    """, (sid,)).fetchone()[0]

    already = db.execute("""
        SELECT 1
        FROM borrowed_books
        WHERE student_id = ?
          AND book_id = ?
          AND returned = 0
    """, (sid, bid)).fetchone()

    if answer == "no":

        if not s["active"]:
            reason = (
                "the student account is inactive."
            )

        elif b["copies"] <= 0:
            reason = (
                "there are no available copies."
            )

        elif count >= 3:
            reason = (
                "the student already has "
                "3 books checked out."
            )

        elif already:
            reason = (
                "the student already has "
                "this book checked out."
            )

        else:
            reason = (
                "a Prolog borrowing rule "
                "did not allow it."
            )

        print(
            f"Library: No, {s['name']} cannot "
            f"borrow {b['title']} because {reason}"
        )

        return reason

    if answer != "yes":
        print(
            "Library: Unexpected response "
            "from Prolog:", answer
        )

        return (
            "the Prolog response could "
            "not be understood."
        )

    if not checkout:

        reason = (
            f"{s['name']} has an active account, "
            f"fewer than 3 loans, and "
            f"{b['copies']} copies are available."
        )

        print(
            f"Library: Yes! {s['name']} "
            f"can borrow {b['title']}."
        )

        return reason

    # Complete the checkout if approved.
    with db:

        updated = db.execute("""
            UPDATE books
            SET copies = copies - 1
            WHERE book_id = ?
              AND copies > 0
        """, (bid,)).rowcount

        if not updated:
            print(
                "Library: The last available copy is gone."
            )

            return (
                "the book no longer has "
                "any available copies."
            )

        today = date.today()
        due = today + timedelta(days=14)

        db.execute("""
            INSERT INTO borrowed_books(
                student_id,
                book_id,
                borrow_date,
                due_date
            )
            VALUES (?, ?, ?, ?)
        """, (
            sid,
            bid,
            today.isoformat(),
            due.isoformat()
        ))

    print(
        f"Library: Checked out {b['title']} "
        f"to {s['name']}. Due: {due}."
    )

    return "the checkout was successful."


# ==========================================
# RETURN BOOKS
# ==========================================

def return_book(db, name, title):

    s = student(db, name)
    b = book(db, title)

    if s is None or b is None:
        print(
            "Library: Student or book not found."
        )
        return

    loan = db.execute("""
        SELECT rowid
        FROM borrowed_books
        WHERE student_id = ?
          AND book_id = ?
          AND returned = 0
        LIMIT 1
    """, (
        s["student_id"],
        b["book_id"]
    )).fetchone()

    if loan is None:
        print(
            "Library: This student doesn't "
            "have that book checked out."
        )
        return

    with db:
        db.execute("""
            UPDATE borrowed_books
            SET returned = 1
            WHERE rowid = ?
        """, (loan[0],))

        db.execute("""
            UPDATE books
            SET copies = copies + 1
            WHERE book_id = ?
        """, (b["book_id"],))

    print(
        f"Library: {b['title']} was returned successfully."
    )


# ==========================================
# BOOK RECOMMENDATIONS
# ==========================================

def recommend(db, name):
    """Get personalized recommendations from Prolog."""

    s = student(db, name)

    if s is None:
        print(
            "Library: Student not found. "
            "Try 'sign up'."
        )
        return

    goal = (
        f"forall(recommend({s['student_id']}, B, Score), "
        "format('~w|~w~n', [B, Score]))"
    )

    output = prolog(db, goal)

    if output is None:
        return

    scores = []

    for line in output.splitlines():

        try:
            bid, points = map(
                int,
                line.split("|")
            )

            scores.append((points, bid))

        except ValueError:
            continue

    if not scores:
        print(
            "Library: No recommendations found. "
            "Try rating a book first."
        )
        return

    print(
        f"\nLibrary: My book recommendations "
        f"for {s['name']}:\n"
    )

    for score, bid in sorted(
        scores,
        reverse=True
    )[:5]:

        b = db.execute("""
            SELECT *
            FROM books
            WHERE book_id = ?
        """, (bid,)).fetchone()

        if b:
            print(
                f"  {b['title']} by {b['author']}"
            )
            print(
                f"  Genre: {b['genre']}"
            )
            print(
                f"  Match score: {score}\n"
            )


# ==========================================
# SIMILAR AUTHORS
# ==========================================

def similar_authors(db, name):

    goal = (
        f"findall(A, "
        f"similar_author({prolog_atom(name.lower())}, A), L),"
        "sort(L, U),"
        "forall(member(A, U), writeln(A))"
    )

    output = prolog(db, goal)

    if output is None:
        return

    if not output:
        print(
            "Library: No similar authors found."
        )
        return

    print(
        "Library: Authors who write similar genres:"
    )

    for author in output.splitlines()[:10]:
        print(" ", author.title())


# ==========================================
# BOOK CLUBS
# ==========================================

def clubs(db):

    goal = (
        "forall(club_match(A, B, G), "
        "format('~w|~w|~w~n', [A, B, G]))"
    )

    output = prolog(db, goal)

    if output is None:
        return

    if not output:
        print(
            "Library: No book club matches yet. "
            "More students can sign up."
        )
        return

    print(
        "\nLibrary: Suggested reading partners:\n"
    )

    for line in output.splitlines()[:15]:

        try:
            sid1, sid2, genre = line.split(
                "|", 2
            )

            names = db.execute("""
                SELECT name
                FROM students
                WHERE student_id IN (?, ?)
                ORDER BY student_id
            """, (
                int(sid1),
                int(sid2)
            )).fetchall()

            if len(names) == 2:
                print(
                    f"  {names[0][0]} and {names[1][0]}"
                    f" - {genre.title()}"
                )

        except ValueError:
            continue


# ==========================================
# PROLOG BORROWING PLAN
# ==========================================

def plan(db):
    """Plan allocations for requested books."""

    requests = db.execute("""
        SELECT student_id, book_id
        FROM requests
        ORDER BY rowid
        LIMIT 8
    """).fetchall()

    if not requests:
        print(
            "Library: No saved requests. "
            "Try 'request The Silent Legacy for Alex'."
        )
        return

    terms = ",".join(
        f"request({r[0]}, {r[1]})"
        for r in requests
    )

    goal = (
        f"best_plan([{terms}], Plan),"
        "forall(member(assigned(S, B), Plan),"
        "format('~w|~w~n', [S, B]))"
    )

    output = prolog(db, goal)

    if output is None:
        return

    if not output:
        print(
            "Library: None of these requests "
            "can be fulfilled right now."
        )
        return

    print(
        "\nLibrary: Prolog's allocation plan:\n"
    )

    for line in output.splitlines():

        try:
            sid, bid = map(
                int,
                line.split("|")
            )

        except ValueError:
            continue

        s = db.execute("""
            SELECT name
            FROM students
            WHERE student_id = ?
        """, (sid,)).fetchone()

        b = db.execute("""
            SELECT title
            FROM books
            WHERE book_id = ?
        """, (bid,)).fetchone()

        if s and b:
            print(
                f"  Give {b[0]} to {s[0]}"
            )


# ==========================================
# CONVERSATIONAL LIBRARY ASSISTANT
# ==========================================

def assistant(db):
    """Understand everyday library questions."""

    print("\nWelcome to ProLogSMARTLIBRARY!")
    print("Your Smart Library Assistant")

    print("\nAsk questions in everyday English.")

    print("\nYou can ask me things like:")
    print('  "Show me science fiction books"')
    print('  "Can Alex borrow The Silent Legacy?"')
    print('  "Recommend books for Alex"')

    print("\nType 'exit' to stop.\n")

    last_book = None
    last_reason = None

    while True:

        try:
            question = input("You: ").strip()

        except (EOFError, KeyboardInterrupt):
            print(
                "\nLibrary: Goodbye! Happy reading!"
            )
            break

        if not question:
            continue

        q = question.rstrip(" ?.!")
        low = q.lower()

        # Exit the program.
        if low in (
            "exit",
            "quit",
            "goodbye"
        ):
            print(
                "Library: Goodbye! Happy reading!"
            )
            break

        # Explain the previous borrowing decision.
        if low in (
            "why",
            "why not",
            "how come"
        ):
            print(
                "Library:",
                last_reason or
                "Ask about borrowing a book first."
            )
            continue

        # ----------------------------------
        # CAN A STUDENT BORROW A BOOK?
        # ----------------------------------

        m = re.fullmatch(
            r"(?:can|could|may)\s+(.+?)"
            r"\s+borrow\s+(.+)",
            q,
            re.I
        )

        if m:
            title = m[2].strip()

            if title.lower() == "it":

                if last_book is None:
                    print(
                        "Library: Which book do you mean?"
                    )
                    continue

                title = last_book

            else:
                last_book = title

            last_reason = eligibility(
                db,
                m[1],
                title
            )

            continue

        # ----------------------------------
        # IS A BOOK AVAILABLE?
        # ----------------------------------

        m = re.fullmatch(
            r"(?:is\s+(.+?)\s+available|"
            r"how many copies of\s+(.+?)"
            r"(?:\s+are available)?)",
            q,
            re.I
        )

        if m:
            title = next(
                g for g in m.groups() if g
            ).strip()

            if title.lower() == "it":

                if last_book is None:
                    print(
                        "Library: Which book do you mean?"
                    )
                    continue

                title = last_book

            else:
                last_book = title

            availability(db, title)
            continue

        # ----------------------------------
        # CHECK OUT A BOOK
        # ----------------------------------

        m = re.fullmatch(
            r"(?:check out|checkout|borrow)"
            r"\s+(.+?)\s+(?:for|to)\s+(.+)",
            q,
            re.I
        )

        if m:
            title = (
                last_book
                if m[1].lower() == "it"
                else m[1]
            )

            if not title:
                print(
                    "Library: Which book do you mean?"
                )
                continue

            last_book = title

            last_reason = eligibility(
                db,
                m[2],
                title,
                checkout=True
            )

            continue

        # ----------------------------------
        # RETURN A BOOK
        # ----------------------------------

        m = re.fullmatch(
            r"return\s+(.+?)"
            r"\s+(?:for|from)\s+(.+)",
            q,
            re.I
        )

        if m:
            return_book(
                db,
                m[2],
                m[1]
            )
            continue

        # ----------------------------------
        # RATE A BOOK
        # ----------------------------------

        m = re.fullmatch(
            r"(?:rate|give)\s+(.+?)"
            r"\s+(?:a\s+)?([1-5])"
            r"\s*(?:stars?)?",
            q,
            re.I
        )

        if m:
            name = input(
                "Library: Student name: "
            ).strip()

            rate(
                db,
                name,
                m[1],
                int(m[2])
            )

            continue

        # ----------------------------------
        # VIRTUAL BOOKMARK
        # ----------------------------------

        m = re.fullmatch(
            r"(?:bookmark|save page)"
            r"\s+(.+?)\s+(?:at\s+)?"
            r"page\s+(\d+)\s+for\s+(.+)",
            q,
            re.I
        )

        if m:
            save_bookmark(
                db,
                m[3],
                m[1],
                int(m[2])
            )
            continue

        # ----------------------------------
        # SHOW BOOKMARKS
        # ----------------------------------

        m = re.fullmatch(
            r"(?:show bookmarks|my bookmarks)"
            r"\s+(?:for\s+)?(.+)",
            q,
            re.I
        )

        if m:
            bookmarks(db, m[1])
            continue

        # ----------------------------------
        # REMINDER MESSAGES
        # ----------------------------------

        m = re.fullmatch(
            r"(?:reminders?|due books)"
            r"\s+(?:for\s+)?(.+)",
            q,
            re.I
        )

        if m:
            reminders(db, m[1])
            continue

        # ----------------------------------
        # PERSONALIZED RECOMMENDATIONS
        # ----------------------------------

        m = re.fullmatch(
            r"(?:recommend|suggest)"
            r"(?:\s+books)?"
            r"\s+(?:for|to)\s+(.+)",
            q,
            re.I
        )

        if m:
            recommend(
                db,
                m[1]
            )
            continue

        # More ways to ask for recommendations.
        m = re.fullmatch(
            r"(?:what should|what can)"
            r"\s+(.+?)\s+read(?: next)?|"
            r"what books?\s+(?:would|might)"
            r"\s+(.+?)\s+like",
            q,
            re.I
        )

        if m:
            name = next(
                g for g in m.groups() if g
            )

            recommend(db, name)
            continue

        # ----------------------------------
        # SIMILAR AUTHORS
        # ----------------------------------

        m = re.fullmatch(
            r"(?:authors similar to|"
            r"authors like|writers like)"
            r"\s+(.+)",
            q,
            re.I
        )

        if m:
            similar_authors(
                db,
                m[1]
            )
            continue

        # ----------------------------------
        # REQUEST A BOOK
        # ----------------------------------

        m = re.fullmatch(
            r"request\s+(.+?)"
            r"\s+for\s+(.+)",
            q,
            re.I
        )

        if m:
            s = student(db, m[2])
            b = book(db, m[1])

            if s is None or b is None:
                print(
                    "Library: Student or book not found."
                )

            else:
                with db:
                    db.execute("""
                        INSERT OR IGNORE INTO requests(
                            student_id,
                            book_id
                        )
                        VALUES (?, ?)
                    """, (
                        s["student_id"],
                        b["book_id"]
                    ))

                print(
                    "Library: Request saved."
                )

            continue

        # ----------------------------------
        # GENERATE A BORROWING PLAN
        # ----------------------------------

        if re.search(
            r"\b(plan requests|borrowing plan)\b",
            low
        ):
            plan(db)
            continue

        # ----------------------------------
        # FIND A BOOK CLUB
        # ----------------------------------

        if re.search(
            r"\b(book club|reading group|clubs)\b",
            low
        ):
            clubs(db)
            continue

        # ----------------------------------
        # STUDENT REGISTRATION
        # ----------------------------------

        if re.search(
            r"\b(sign up|signup|register|join library)\b",
            low
        ):
            register(db)
            continue

        # ----------------------------------
        # UNCLEAR RECOMMENDATION QUESTION
        # ----------------------------------

        if re.search(
            r"\b(recommend|suggest)\b",
            low
        ):
            print(
                "Library: Try "
                "'recommend books for Alex'."
            )
            continue

        # ----------------------------------
        # REMEMBER BOOK TITLES
        # ----------------------------------

        for candidate in db.execute(
            "SELECT title FROM books"
        ):

            if candidate[0].lower() in low:
                last_book = candidate[0]
                break

        # ----------------------------------
        # GENERAL BOOK SEARCH
        # ----------------------------------

        search_books(db, question)


# ==========================================
# START PROGRAM
# ==========================================

if __name__ == "__main__":

    with connect() as database:

        initialize(database)

        assistant(database)
