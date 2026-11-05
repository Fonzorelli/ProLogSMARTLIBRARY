
% ProLogSMARTLIBRARY
% COSC 430 - Book Recommendations

:- dynamic favorite_genre/2.
:- dynamic book_genre/2.
:- dynamic book_author/2.
:- dynamic book_pages/2.
:- dynamic keyword/2.
:- dynamic rated/3.

% A liked book has a rating of 4 or 5.

liked(S, B) :-
    rated(S, B, Stars),
    Stars >= 4.


% Book recommendation scoring:
%
% Favorite author: 6 points
% Favorite genre:  5 points
% Shared keyword:  2 points
% Similar length:  1 point

recommend(S, B, Score) :-
    book(B, Copies),
    Copies > 0,

    \+ rated(S, B, _),
    \+ loan(S, B),

    (
        favorite_genre(S, G),
        book_genre(B, G)
    ->
        Genre = 5
    ;
        Genre = 0
    ),

    (
        liked(S, Old1),
        book_author(Old1, A),
        book_author(B, A),
        Old1 \= B
    ->
        Author = 6
    ;
        Author = 0
    ),

    (
        liked(S, Old2),
        keyword(Old2, K),
        keyword(B, K),
        Old2 \= B
    ->
        Words = 2
    ;
        Words = 0
    ),

    (
        liked(S, Old3),
        book_pages(Old3, P),
        book_pages(B, Q),
        Old3 \= B,
        Diff is abs(P - Q),
        Diff =< 100
    ->
        Length = 1
    ;
        Length = 0
    ),

    Score is Genre + Author + Words + Length,
    Score > 0.


% Find authors writing in the same genre.

similar_author(A1, A2) :-
    book_author(B1, A1),
    book_genre(B1, G),
    book_author(B2, A2),
    book_genre(B2, G),
    A1 \= A2.


% Match readers who enjoy the same genre.

club_match(S1, S2, G) :-
    student(S1, active),
    student(S2, active),
    S1 < S2,
    favorite_genre(S1, G),
    favorite_genre(S2, G).
