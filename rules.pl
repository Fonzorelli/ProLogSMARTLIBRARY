
% ProLogSMARTLIBRARY
% COSC 430 - Borrowing and Planning

:- dynamic student/2.
:- dynamic book/2.
:- dynamic loan_count/2.
:- dynamic loan/2.

% A student may borrow if the account is active,
% copies are available, and the limit is not reached.

can_borrow(Student, Book) :-
    student(Student, active),
    book(Book, Copies),
    Copies > 0,
    loan_count(Student, Count),
    Count < 3,
    \+ loan(Student, Book).


% Generate possible borrowing plans.

allocation([], Plan, Plan).

% Try assigning the book.
allocation(
    [request(S, B)|Rest],
    SoFar,
    Plan
) :-
    can_borrow(S, B),
    book(B, Copies),
    count_book(B, SoFar, Used),
    Used < Copies,
    loan_count(S, Existing),
    count_student(S, SoFar, Added),
    Existing + Added < 3,
    allocation(
        Rest,
        [assigned(S, B)|SoFar],
        Plan
    ).

% Or skip the request.
allocation([_|Rest], SoFar, Plan) :-
    allocation(Rest, SoFar, Plan).


% Count assigned copies of one book.

count_book(_, [], 0).

count_book(B, [assigned(_, B)|Rest], N) :-
    !,
    count_book(B, Rest, M),
    N is M + 1.

count_book(B, [_|Rest], N) :-
    count_book(B, Rest, N).


% Count assignments for one student.

count_student(_, [], 0).

count_student(S, [assigned(S, _)|Rest], N) :-
    !,
    count_student(S, Rest, M),
    N is M + 1.

count_student(S, [_|Rest], N) :-
    count_student(S, Rest, N).


% Select the plan with the most assignments.

best_plan(Requests, Best) :-
    findall(
        P,
        allocation(Requests, [], P),
        Plans
    ),
    choose_longest(Plans, [], Best).


choose_longest([], Best, Best).

choose_longest([P|Rest], Current, Best) :-
    length(P, A),
    length(Current, B),
    (
        A > B ->
        Next = P
    ;
        Next = Current
    ),
    choose_longest(Rest, Next, Best).
