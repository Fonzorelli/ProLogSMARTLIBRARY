
"""Generate fictional library books."""

import random
import sqlite3
from pathlib import Path

DB = Path(__file__).resolve().parent / "library.db"

GENRES = {
    "Mystery": "detective clues secrets crime",
    "Fantasy": "magic dragons kingdoms adventure",
    "Science Fiction": "robots space ai future",
    "Romance": "love relationships friendship",
    "Horror": "ghosts suspense darkness",
    "History": "civilization culture history",
    "Technology": "coding computers databases",
    "Adventure": "exploration travel journey",
    "Sports": "football basketball teamwork",
    "Young Adult": "school friendship identity"
}

ADJECTIVES = [
    "Hidden", "Silent", "Golden", "Midnight",
    "Forgotten", "Secret", "Brave",
    "Distant", "Rising", "Last"
]

SUBJECTS = [
    "Journey", "Puzzle", "Horizon", "Legacy",
    "World", "Discovery", "Promise",
    "Signal", "Adventure", "Story"
]

AUTHORS = [
    "Jordan Brooks", "Avery Reed",
    "Taylor Parker", "Morgan Bennett",
    "Casey Hayes", "Riley Clark",
    "Jamie Howard", "Quinn Foster",
    "Cameron Price", "Skyler Morris"
]


def main():
    random.seed(430)

    with sqlite3.connect(DB) as db:
        db.execute("""
            CREATE TABLE IF NOT EXISTS books (
                book_id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                author TEXT NOT NULL,
                genre TEXT NOT NULL,
                pages INTEGER NOT NULL,
                keywords TEXT,
                copies INTEGER DEFAULT 1
            )
        """)

        added = 0

        for i, (genre, keywords) in enumerate(
            GENRES.items()
        ):
            for j in range(10):
                title = (
                    f"The {ADJECTIVES[j]} "
                    f"{SUBJECTS[(i + j) % 10]}"
                )

                author = AUTHORS[(i + j) % 10]

                exists = db.execute("""
                    SELECT 1 FROM books
                    WHERE title=? AND author=? AND genre=?
                """, (
                    title, author, genre
                )).fetchone()

                if exists:
                    continue

                db.execute("""
                    INSERT INTO books(
                        title, author, genre,
                        pages, keywords, copies
                    )
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (
                    title, author, genre,
                    random.randint(120, 620),
                    keywords,
                    random.randint(0, 5)
                ))

                added += 1

        total = db.execute(
            "SELECT COUNT(*) FROM books"
        ).fetchone()[0]

        print(f"Added {added} books.")
        print(f"Total books: {total}")


if __name__ == "__main__":
    main()
