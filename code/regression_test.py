#!/usr/bin/env python3
"""Cross-chapter regression tests for the Cave Terror text adventure.

Drives every chapter version of the game (ch10-ch15) as a subprocess with
one shared harness and checks that, consistently across all versions:

* input normalization: commands work regardless of letter case and
  surrounding whitespace;
* unknown commands produce an understandable error ("Invalid action!")
  without breaking the main loop;
* state transitions (movement, combat, healing, gold, trading, victory)
  behave the same way from version to version;
* each chapter still runs standalone and reaches a clean exit on victory
  (ch10 has no world yet, so it is terminated after its checks).

Requires a POSIX system (uses select() on pipes). Run with:

    python3 regression_test.py
"""

import os
import select
import subprocess
import sys
import time

CODE_DIR = os.path.dirname(os.path.abspath(__file__))

# Fixed seed so enemy placement and gold amounts are deterministic.
# With this seed the walkthrough path in ch14/ch15 only meets beatable
# enemies (three spiders and one ogre).
RANDOM_SEED = 7


class GameSession:
    """A running chapter game process that we can converse with."""

    def __init__(self, chapter):
        launcher = (
            "import random; random.seed(%d); "
            "exec(compile(open('game.py').read(), 'game.py', 'exec'))"
            % RANDOM_SEED
        )
        self.proc = subprocess.Popen(
            [sys.executable, "-u", "-c", launcher],
            cwd=os.path.join(CODE_DIR, chapter),
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
        )
        self.buffer = ""
        self.mark = 0

    def _pump(self, timeout):
        ready, _, _ = select.select([self.proc.stdout], [], [], timeout)
        if ready:
            chunk = os.read(self.proc.stdout.fileno(), 4096)
            if chunk:
                self.buffer += chunk.decode("utf-8", errors="replace")

    def _wait_for(self, predicate, description, timeout):
        deadline = time.monotonic() + timeout
        while not predicate():
            if self.proc.poll() is not None:
                self._pump(0.3)
                if predicate():
                    return
                raise AssertionError(
                    "game exited while waiting for %s\n"
                    "---- game output ----\n%s" % (description, self.buffer))
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise AssertionError(
                    "timed out waiting for %s\n"
                    "---- game output ----\n%s" % (description, self.buffer))
            self._pump(min(remaining, 0.1))

    def expect(self, text, timeout=15):
        """Wait until text appears anywhere in the output so far."""
        self._wait_for(lambda: text in self.buffer, repr(text), timeout)

    def expect_recent(self, text, timeout=15):
        """Wait until text appears in output since the last checkpoint."""
        self._wait_for(lambda: text in self.recent(), repr(text), timeout)

    def send(self, line=""):
        self.proc.stdin.write((line + "\n").encode())
        self.proc.stdin.flush()

    def say(self, line, expect=None, timeout=15):
        """Send input and expect a response in the fresh output."""
        self.checkpoint()
        self.send(line)
        if expect is not None:
            self.expect_recent(expect, timeout)

    def command(self, line, response=None, timeout=15):
        """Send a main-loop command and wait for the fresh Action: prompt."""
        self.checkpoint()
        prompt_count = self.buffer.count("Action: ")
        self.send(line)
        if response is not None:
            self.expect_recent(response, timeout)
        self.wait_prompt(timeout, prompt_count)

    def wait_prompt(self, timeout=15, since=None):
        """Wait for an Action: prompt beyond the count captured in `since`."""
        if since is None:
            since = self.buffer.count("Action: ")
        self._wait_for(
            lambda: self.buffer.count("Action: ") > since,
            "the next 'Action: ' prompt", timeout)

    def checkpoint(self):
        self.mark = len(self.buffer)

    def recent(self):
        return self.buffer[self.mark:]

    def expect_clean_exit(self, timeout=15):
        try:
            returncode = self.proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            self.proc.kill()
            raise AssertionError(
                "game kept running instead of ending\n"
                "---- game output ----\n%s" % self.buffer)
        self._pump(0.3)
        if returncode != 0:
            raise AssertionError(
                "game exited with status %s\n"
                "---- game output ----\n%s" % (returncode, self.buffer))

    def stop(self):
        if self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.proc.kill()


# ---------------------------------------------------------------------------
# Checks shared by every chapter version
# ---------------------------------------------------------------------------

def check_unknown_command_keeps_loop_alive(game):
    """Unknown or blank input -> understandable error, loop keeps running."""
    game.expect("Action: ")
    game.command("xyzzy", "Invalid action!")
    game.command("   ", "Invalid action!")
    if game.proc.poll() is not None:
        raise AssertionError("main loop stopped on unknown command\n"
                             "---- game output ----\n%s" % game.buffer)


def check_inventory_normalization(game):
    """Whitespace and letter case are normalized before dispatch."""
    game.command(" I ", "Inventory:")


def fight_until_dead(game, max_rounds=30):
    """Attack until the enemy in the current room dies."""
    for _ in range(max_rounds):
        game.command("a")
        if "You killed" in game.recent():
            return
    raise AssertionError("fight did not end\n"
                         "---- game output ----\n%s" % game.buffer)


def heal_with_bad_choice_first(game):
    """The heal menu rejects out-of-range choices instead of wrapping."""
    prompt_count = game.buffer.count("Action: ")
    game.send("h")
    game.expect("Choose an item to use to heal:")
    game.say("0", "Invalid choice, try again.")
    game.say("1", "Current HP:")
    game.wait_prompt(since=prompt_count)


# ---------------------------------------------------------------------------
# Per-chapter walkthroughs
# ---------------------------------------------------------------------------

def play_ch10(game):
    game.expect("Escape from Cave Terror!")
    check_unknown_command_keeps_loop_alive(game)
    check_inventory_normalization(game)
    game.command(" N ", "Go North!")
    # ch10 has no world or victory condition yet; stop the endless loop.
    game.stop()


def play_ch11(game):
    game.expect("Escape from Cave Terror!")
    check_unknown_command_keeps_loop_alive(game)
    check_inventory_normalization(game)
    game.command(" N ", "boring part of the cave")   # (1,1)
    game.command("e", "You can't go that way!")      # off-map move refused
    game.command("s", "flickering torch")            # (1,2) start
    game.command("e", "boring part of the cave")     # (2,2)
    game.command("e", "You can't go that way!")      # off-map move refused
    game.command("w")                                # (1,2)
    game.command("n")                                # (1,1)
    game.send("n")                                   # (1,0) victory tile
    game.expect("Victory is yours!")
    game.expect_clean_exit()


def play_ch12(game):
    game.expect("Escape from Cave Terror!")
    check_unknown_command_keeps_loop_alive(game)
    check_inventory_normalization(game)
    game.command("a", "nothing to attack")           # no enemy on start tile
    prompt_count = game.buffer.count("Action: ")
    game.send("h")
    game.expect("Choose an item to use to heal:")
    game.say("0", "Invalid choice, try again.")      # no negative-index wrap
    game.say("1", "Current HP: 100")
    game.wait_prompt(since=prompt_count)
    game.command(" N ", "Enemy does")                # (1,1) enemy room
    fight_until_dead(game)
    game.send("n")                                   # (1,0) victory tile
    game.expect("Victory is yours!")
    game.expect_clean_exit()


def play_ch13(game):
    game.expect("Escape from Cave Terror!")
    check_unknown_command_keeps_loop_alive(game)
    check_inventory_normalization(game)
    game.command(" N ", "a: Attack")                 # (1,1) enemy blocks path
    game.command("n", "Invalid action!")             # can't flee a live enemy
    fight_until_dead(game)
    game.send("n")                                   # (1,0) victory tile
    game.expect("Victory is yours!")
    game.expect_clean_exit()


def visit_trader(game, sell_item=None):
    """Exercise the trade menus; out-of-range choices must not crash."""
    game.say("t", "(B)uy, (S)ell, or (Q)uit?")
    game.say("b", "Choose an item or press Q to exit:")
    game.say("0", "Invalid choice!")
    game.say("99", "Invalid choice!")
    game.say("q", "(B)uy, (S)ell, or (Q)uit?")
    if sell_item is not None:
        game.say("s", "Choose an item or press Q to exit:")
        game.say(str(sell_item), "Trade complete!")
        game.say("q", "(B)uy, (S)ell, or (Q)uit?")
    game.say("q", "Action: ")


def check_gold_only_handled_once(game):
    """Revisiting a FindGoldTile must not hand out gold twice."""
    game.command("w", "unremarkable part of the cave")  # (3,3) revisited
    if "gold added" in game.recent():
        raise AssertionError("gold was handed out twice on the same tile")
    game.command("e")                                # back to (4,3)


def play_ch14(game):
    game.expect("Escape from Cave Terror!")
    check_unknown_command_keeps_loop_alive(game)
    check_inventory_normalization(game)
    game.command(" E ", "gold added")                # (3,3) find gold
    game.command("e", "a: Attack")                   # (4,3) enemy guards trader
    fight_until_dead(game)
    check_gold_only_handled_once(game)
    game.command("n", "willing to trade")            # (4,2) trader tile
    visit_trader(game, sell_item=3)                  # sell the Crusty Bread
    game.command("n", "a: Attack")                   # (4,1) enemy
    fight_until_dead(game)
    game.command("n", "a: Attack")                   # (4,0) enemy
    fight_until_dead(game)
    game.command("w", "a: Attack")                   # (3,0) enemy guards exit
    fight_until_dead(game)
    game.send("w")                                   # (2,0) victory tile
    game.expect("Victory is yours!")
    game.expect_clean_exit()


def play_ch15(game):
    game.expect("Escape from Cave Terror!")
    check_unknown_command_keeps_loop_alive(game)
    check_inventory_normalization(game)
    game.command(" E ", "gold added")                # (3,3) find gold
    game.command("e", "a: Attack")                   # (4,3) enemy guards trader
    fight_until_dead(game)
    heal_with_bad_choice_first(game)                 # hurt -> heal is offered
    check_gold_only_handled_once(game)
    game.command("n", "willing to trade")            # (4,2) trader tile
    visit_trader(game)                               # keep bread for healing
    game.command("n", "a: Attack")                   # (4,1) enemy
    fight_until_dead(game)
    game.command("n", "a: Attack")                   # (4,0) enemy
    fight_until_dead(game)
    game.command("w", "a: Attack")                   # (3,0) enemy guards exit
    fight_until_dead(game)
    game.send("w")                                   # (2,0) victory tile
    game.expect("Victory is yours!")
    game.expect_clean_exit()


CHAPTERS = [
    ("ch10_intermezzo", play_ch10),
    ("ch11_world", play_ch11),
    ("ch12_enemies", play_ch12),
    ("ch13_world2", play_ch13),
    ("ch14_economy", play_ch14),
    ("ch15_endgame", play_ch15),
]


def main():
    failures = 0
    for chapter, scenario in CHAPTERS:
        game = GameSession(chapter)
        try:
            scenario(game)
        except AssertionError as exc:
            failures += 1
            print("FAIL %s\n%s" % (chapter, exc))
        else:
            print("PASS %s" % chapter)
        finally:
            game.stop()
    if failures:
        print("\n%d of %d chapters failed." % (failures, len(CHAPTERS)))
        return 1
    print("\nAll %d chapters passed." % len(CHAPTERS))
    return 0


if __name__ == "__main__":
    sys.exit(main())
