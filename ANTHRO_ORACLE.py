
#!/usr/bin/env python3
"""
ANTHRO_ORACLE.py — Furry Anthro Divination (deterministic, cryptographically salted)

Update (v1.1):
- Fixed "hang after question": previously ran PBKDF2 **per token** (96x by default), which is very slow.
- Now does PBKDF2 **once per query** to derive a master key (still 888,888 iterations),
  then uses fast HMAC-SHA256 per token. Same determinism, much faster UX.
- Added clear status updates / progress (Rich progress bar if available, else text).

Usage:
    python3 ANTHRO_ORACLE.py
Options:
    -n, --number      Number of totems to reveal (1, 3, or 5). If omitted, you'll be prompted.
    -s, --size        Size of the hash pool to display (default 96).
    -r, --reversals   Enable shadow/aspect flips (doubles pool variety).
"""

from __future__ import annotations
import argparse
import hashlib
import hmac
import sys
from dataclasses import dataclass
from typing import Dict, List, Tuple
import random
import time

# ----- Optional color UI via rich -----
try:
    from rich.console import Console
    from rich.table import Table
    from rich.panel import Panel
    from rich.progress import Progress, SpinnerColumn, BarColumn, TextColumn, TimeElapsedColumn
    console = Console()
    RICH_AVAILABLE = True
except Exception:
    RICH_AVAILABLE = False

# ====== Security / Hashing ======
class ProtectiveHasher:
    PROTECTION_ITERATIONS = 888_888
    HASH_LENGTH = 32

    @staticmethod
    def derive_master(base_bytes: bytes, salt_bytes: bytes) -> bytes:
        """
        One PBKDF2-HMAC-SHA256 derivation per query to obtain a master key.
        """
        try:
            return hashlib.pbkdf2_hmac(
                'sha256', base_bytes, salt_bytes,
                ProtectiveHasher.PROTECTION_ITERATIONS,
                dklen=ProtectiveHasher.HASH_LENGTH
            )
        except Exception as e:
            # Fallback: iterative SHA256 (very slow but preserves determinism)
            out = base_bytes
            for _ in range(ProtectiveHasher.PROTECTION_ITERATIONS):
                out = hashlib.sha256(out + salt_bytes).digest()
            return out[:ProtectiveHasher.HASH_LENGTH]

    @staticmethod
    def hmac_token(master_key: bytes, token_salt: bytes) -> bytes:
        return hmac.new(master_key, token_salt, hashlib.sha256).digest()

    @staticmethod
    def seed_from_query(query: str) -> bytes:
        return hashlib.sha256(query.encode('utf-8')).digest()


# ====== Anthro Oracle Data ======
SPECIES = [
    # Mammals
    "Wolf", "Fox", "Dog", "Cat", "Lion", "Tiger", "Leopard", "Cheetah",
    "Hyena", "Bear", "Otter", "Raccoon", "Red Panda", "Husky", "Coyote",
    "Jackal", "Rabbit", "Hare", "Deer", "Stag", "Moose", "Bison", "Horse",
    "Goat", "Sheep", "Boar", "Bat",
    # Avian / Reptile / Other
    "Eagle", "Raven", "Owl", "Hawk", "Crow", "Swan", "Phoenix",
    "Dragon", "Lizard", "Gecko", "Snake", "Cobra", "Crocodile",
    "Shark", "Dolphin", "Orca", "Seal"
]

ROLES = [
    "Guardian", "Healer", "Seer", "Warrior", "Trickster", "Bard",
    "Scholar", "Builder", "Navigator", "Shaman", "Alchemist",
    "Diplomat", "Scout", "Hermit", "Caretaker"
]

ELEMENTS = [
    "Fire", "Water", "Earth", "Air", "Storm", "Wood", "Metal", "Light", "Shadow", "Aether"
]

VIRTUES = [
    "Courage", "Devotion", "Compassion", "Patience", "Integrity",
    "Curiosity", "Discipline", "Joy", "Humility", "Grace",
    "Perseverance", "Wisdom", "Playfulness", "Ingenuity", "Justice"
]

SHADOWS = [
    "Fear", "Control", "Apathy", "Doubt", "Pride",
    "Impatience", "Isolation", "Resentment", "Greed", "Confusion",
    "Rigidity", "Escapism", "Despair", "Deceit", "Chaos"
]

GIFTS = [
    "Moonstep (move between feelings without losing center)",
    "Sunheart (radiate safety to those nearby)",
    "Scent of Truth (sense honest intent)",
    "Starcall (hear guidance in silence)",
    "Packbond (summon allies through trust)",
    "Mirrorshine (reflect harm back as lesson)",
    "Driftwood (float above old patterns)",
    "Pawprint Path (track the next right step)",
    "Thunderpaw (break stagnation kindly)",
    "Sea-breath (soften grief into flow)",
    "Keenwhisker (notice the subtle invitation)",
    "Bloomcloak (protect new beginnings)",
    "Stonebed (rest deeply, wake clear)",
    "Kindlefang (ignite shared motivation)",
    "Skyweave (connect distant hearts)"
]

ASPECTS = ["Upright", "Shadowed"]  # Shadowed shown only if reversals enabled

# ====== Core Types ======
@dataclass(frozen=True)
class Totem:
    species: str
    role: str
    element: str
    virtue: str
    shadow: str
    gift: str
    aspect: str
    digest: str  # full hex digest
    token: str   # short token (first 8 hex)

# ====== Oracle Engine ======
class AnthroOracle:
    def __init__(self, reversals: bool):
        self.reversals = reversals
        self.hasher = ProtectiveHasher()

    def _choice_from_digest(self, digest: bytes, pool: List[str], offset: int) -> str:
        idx = digest[offset % len(digest)]
        return pool[idx % len(pool)]

    def _build_totem(self, master_key: bytes, idx: int) -> Totem:
        token_salt = f"token-{idx}".encode('utf-8')
        digest = self.hasher.hmac_token(master_key, token_salt)
        hex_digest = digest.hex()
        token = hex_digest[:8]

        species = self._choice_from_digest(digest, SPECIES, 0)
        role    = self._choice_from_digest(digest, ROLES, 5)
        element = self._choice_from_digest(digest, ELEMENTS, 9)
        virtue  = self._choice_from_digest(digest, VIRTUES, 13)
        shadow  = self._choice_from_digest(digest, SHADOWS, 17)
        gift    = self._choice_from_digest(digest, GIFTS, 23)

        if self.reversals:
            aspect = ASPECTS[digest[-1] & 1]
        else:
            aspect = "Upright"

        return Totem(
            species=species, role=role, element=element, virtue=virtue,
            shadow=shadow, gift=gift, aspect=aspect, digest=hex_digest, token=token
        )

    def build_pool(self, query: str, pool_size: int, status_cb=None) -> Dict[str, Totem]:
        base_seed = self.hasher.seed_from_query(query)

        # Derive master once (expensive)
        if status_cb: status_cb("Deriving master hash (888,888 iters)...")
        master_key = self.hasher.derive_master(base_seed, b"anthro-oracle-v1")

        # Deterministic ordering based on base_seed
        rng = random.Random(base_seed)
        count = pool_size * (2 if self.reversals else 1)
        order = list(range(count))
        rng.shuffle(order)

        # Build totems with progress
        deck: Dict[str, Totem] = {}
        for i, pos in enumerate(order):
            if status_cb: status_cb(f"Forging tokens {i+1}/{count}...")
            totem = self._build_totem(master_key, pos)
            # Ensure token uniqueness; on collision, perturb via index
            while totem.token in deck:
                pos += 1
                totem = self._build_totem(master_key, pos)
            deck[totem.token] = totem
        return deck


# ====== UI ======
def print_pool(deck: Dict[str, Totem], columns: int = 4):
    tokens = list(deck.keys())
    if RICH_AVAILABLE:
        table = Table(title="Choose by Token (hash prefixes)", show_lines=False, pad_edge=False)
        for _ in range(columns):
            table.add_column(justify="center", style="cyan")
        rows = [tokens[i:i+columns] for i in range(0, len(tokens), columns)]
        for row in rows:
            table.add_row(*[f"[{t}]" for t in row])
        console.print(table)
    else:
        for i in range(0, len(tokens), columns):
            print("  ".join(f"[{t}]" for t in tokens[i:i+columns]))

def show_totems(totems: List[Totem], query: str):
    positions = {
        1: ["Heart of the Matter"],
        3: ["Path", "Obstacle", "Ally"],
        5: ["Situation", "Challenge", "Guidance", "Support", "Outcome"]
    }
    labels = positions.get(len(totems), [f"Totem #{i+1}" for i in range(len(totems))])

    if RICH_AVAILABLE:
        console.rule("[bold violet]🐾 Anthro Oracle Reading 🐾[/bold violet]")
        console.print(f"[dim]Query:[/dim] {query}")
        for i, t in enumerate(totems):
            title = f"[bold]{labels[i]}[/bold] — {t.token}"
            body = (
                f"[bold]{t.aspect} {t.species} {t.role}[/bold]  •  [italic]{t.element}[/italic]\n"
                f"[dim]Virtue:[/dim] {t.virtue}   [dim]Shadow:[/dim] {t.shadow}\n"
                f"[dim]Gift:[/dim] {t.gift}\n"
                f"[dim]Auth:[/dim] {t.digest[:8].upper()}"
            )
            console.print(Panel(body, title=title, border_style="magenta"))
    else:
        print("\n=== Anthro Oracle Reading ===")
        print(f"Query: {query}")
        for i, t in enumerate(totems):
            label = labels[i] if i < len(labels) else f"Totem #{i+1}"
            print(f"\n--- {label} — {t.token} ---")
            print(f"{t.aspect} {t.species} {t.role} • {t.element}")
            print(f"Virtue: {t.virtue} | Shadow: {t.shadow}")
            print(f"Gift: {t.gift}")
            print(f"Auth: {t.digest[:8].upper()}")


def run_interactive(args):
    def status_text(msg):
        if not RICH_AVAILABLE:
            print(msg)
        # Rich progress handled separately

    # Intro
    if RICH_AVAILABLE:
        console.print("[bold]Welcome to the Anthro Oracle 🐾[/bold]")
        if args.reversals:
            console.print("[dim]Shadow aspects are [green]ENABLED[/green].[/dim]")
        query = console.input("[bold cyan]Ask your sacred question:[/bold cyan] ").strip()
    else:
        print("Welcome to the Anthro Oracle 🐾")
        if args.reversals:
            print("Shadow aspects are ENABLED.")
        query = input("Ask your sacred question: ").strip()

    if not query:
        print("A question is required.", file=sys.stderr)
        sys.exit(1)

    oracle = AnthroOracle(reversals=args.reversals)

    # Number of totems
    num = args.number
    if num is None:
        while True:
            try:
                num = int(input("How many totems? (1, 3, or 5): ").strip())
                if num in (1,3,5):
                    break
            except Exception:
                pass
            print("Please enter 1, 3, or 5.")
    else:
        if num not in (1,3,5):
            print("Error: --number must be 1, 3, or 5.", file=sys.stderr)
            sys.exit(1)

    # Build deck with status
    if RICH_AVAILABLE:
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TimeElapsedColumn(),
            console=console,
            transient=True
        ) as progress:
            task = progress.add_task("Preparing...", total=None)
            last_desc = ["Preparing..."]

            def rich_status(desc):
                # update description only when it changes to avoid spam
                if last_desc[0] != desc:
                    last_desc[0] = desc
                    progress.update(task, description=desc)

            deck = oracle.build_pool(query, args.size, status_cb=rich_status)
            progress.update(task, description="Done")
    else:
        deck = oracle.build_pool(query, args.size, status_cb=status_text)

    # Show pool and prompt
    if RICH_AVAILABLE:
        console.print("\nPick your tokens by hash prefix (3+ chars).")
    else:
        print("\nPick your tokens by hash prefix (3+ chars).")
    print_pool(deck)

    while True:
        raw = input(f"Enter {num} token prefixes (comma-separated): ").strip()
        choices = [c.strip().lower() for c in raw.split(",") if c.strip()]
        if len(choices) != num:
            print(f"Please enter exactly {num} prefixes.")
            continue
        if any(len(c) < 3 for c in choices):
            print("All prefixes must be at least 3 characters.")
            continue
        break

    # Resolve choices
    tokens = list(deck.keys())
    picks: List[Totem] = []
    for pref in choices:
        matches = [t for t in tokens if t.startswith(pref)]
        if len(matches) == 1:
            tok = matches[0]
            picks.append(deck[tok])
            tokens.remove(tok)
        elif len(matches) == 0:
            print(f"No match for '{pref}'. Reading aborted.", file=sys.stderr)
            sys.exit(1)
        else:
            print(f"Ambiguous prefix '{pref}'. Reading aborted.", file=sys.stderr)
            sys.exit(1)

    # Display
    show_totems(picks, query)


def main():
    parser = argparse.ArgumentParser(
        description="Furry Anthro Oracle — interactive, deterministic divination via cryptographic hashing.",
        formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument('-n', '--number', type=int, help='Number of totems to reveal (1, 3, or 5).')
    parser.add_argument('-s', '--size', type=int, default=96, help='Hash pool size to display (default 96).')
    parser.add_argument('-r', '--reversals', action='store_true', help='Enable shadow/aspect reversals.')
    args = parser.parse_args()
    try:
        run_interactive(args)
    except KeyboardInterrupt:
            print("\nReading cancelled.")
            sys.exit(0)
    except SystemExit as e:
        raise e
    except Exception as e:
        print(f"Unexpected error: {e}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()
