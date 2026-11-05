
"""ProLogSMARTLIBRARY community features."""
from datetime import date, timedelta
import sqlite3


def student(db, name):
    return db.execute("""
        SELECT * FROM students
        WHERE name=? COLLATE NOCASE
    """, (name,)).fetchone()


def book(db, title):
    return db.execute("""
        SELECT * FROM books
        WHERE title=? COLLATE NOCASE
    """, (title,)).fetchone()


def register(db):
    name = input("Name: ").strip()

    if not name:
        print("Library: Name is required.")
        return

    age_text = input("Age (optional): ").strip()

    if age_text and (
        not age_text.isdigit() or int(age_text) > 120
    ):
        print("Library: Invalid age.")
        return

    email = input("Email (optional): ").strip() or None
    phone = input("Phone (optional): ").strip() or None
    genre = input("Favorite genre: ").strip() or None

    choice = input(
        "Preview reminders? (yes/no): "
    ).strip().lower()

    opt_in = choice in ("yes", "y")

    try:
        with db:
            db.execute("""
                INSERT INTO students(
                    name, age, email, phone,
                    favorite_genre, active, reminders
                )
                VALUES (?, ?, ?, ?, ?, 1, ?)
            """, (
                name,
                int(age_text) if age_text else None,
                email, phone, genre, int(opt_in)
            ))

        print(f"Library: Welcome, {name}!")

    except sqlite3.IntegrityError:
        print("Library: Email already registered.")


def rate(db, name, title, stars):
    s = student(db, name)
    b = book(db, title)

    if not s or not b:
        print("Library: Student or book not found.")
        return

    with db:
        db.execute("""
            INSERT INTO ratings VALUES (?, ?, ?)
            ON CONFLICT(student_id, book_id)
            DO UPDATE SET rating=excluded.rating
        """, (s["student_id"], b["book_id"], stars))

    print(f"Library: Saved {stars}/5 stars.")


def save_bookmark(db, name, title, page):
    s = student(db, name)
    b = book(db, title)

    if not s or not b:
        print("Library: Student or book not found.")
        return

    if not 0 <= page <= b["pages"]:
        print(
            f"Library: Page must be between "
            f"0 and {b['pages']}."
        )
        return

    with db:
        db.execute("""
            INSERT INTO bookmarks VALUES (?, ?, ?)
            ON CONFLICT(student_id, book_id)
            DO UPDATE SET
            current_page=excluded.current_page
        """, (s["student_id"], b["book_id"], page))

    print(
        f"Library: Bookmark saved at page {page} "
        f"of {b['pages']} "
        f"({page / b['pages']:.0%})."
    )


def bookmarks(db, name):
    s = student(db, name)

    if not s:
        print("Library: Student not found.")
        return

    rows = db.execute("""
        SELECT b.title, m.current_page, b.pages
        FROM bookmarks m
        JOIN books b ON b.book_id=m.book_id
        WHERE m.student_id=?
    """, (s["student_id"],)).fetchall()

    if not rows:
        print("Library: No bookmarks saved.")

    for title, page, total in rows:
        print(
            f"Library: {title}: page {page} "
            f"of {total} ({page / total:.0%})"
        )


def reminders(db, name):
    s = student(db, name)

    if not s:
        print("Library: Student not found.")
        return

    if not s["reminders"]:
        print("Library: Reminders are not enabled.")
        return

    due_before = (
        date.today() + timedelta(days=3)
    ).isoformat()

    rows = db.execute("""
        SELECT b.title, l.due_date
        FROM borrowed_books l
        JOIN books b ON b.book_id=l.book_id
        WHERE l.student_id=?
          AND l.returned=0
          AND l.due_date<=?
    """, (
        s["student_id"], due_before
    )).fetchall()

    if not rows:
        print("Library: Nothing due soon or overdue.")
        return

    print("Library: Reminder preview:")

    for title, due in rows:
        print(f"  {title} is due {due}")

    print("No email or text was sent.")
