# Apress Source Code

This repository accompanies [*Make Your Own Python Text Adventure*](http://www.apress.com/9781484232309) by Phillip Johnson (Apress, 2018).

[comment]: #cover


Download the files as a zip using the green button, or clone the repository to your machine using Git.

## Releases

Release v1.0 corresponds to the code in the published book, without corrections or updates.

## Regression tests

`code/regression_test.py` drives each chapter version of the game (ch10-ch15)
as a subprocess and verifies that input normalization (letter case,
whitespace, unknown commands) and state transitions (movement, combat,
healing, gold, trading, victory) behave consistently across versions. Run it
with:

    python3 code/regression_test.py

## Contributions

See the file Contributing.md for more information on how you can contribute to this repository.
