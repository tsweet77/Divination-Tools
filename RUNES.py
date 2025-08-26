#!/usr/bin/env python3
"""
RUNES.py — Secure deterministic Elder Futhark divination via cryptographic hashing.

This tool provides rune castings using a method that derives results directly from
the user's query and a salt. It employs PBKDF2 key derivation with a high
iteration count (888,888) to ensure the results are both deterministic (repeatable
for the same query) and cryptographically secure against interference.

The casting process simulates drawing runes from a bag without replacement.

Usage:
    python3 RUNES.py -q "Your question here"
    python3 RUNES.py -q "What should I focus on this week?" -n 3
"""

from __future__ import annotations
import argparse
import hashlib
import json
import sys
import logging
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Dict, Any

# Configure logging
logging.basicConfig(level=logging.WARNING, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)

# Pretty output support
try:
    from rich.console import Console
    from rich.panel import Panel
    from rich.text import Text
    console = Console()
    RICH_AVAILABLE = True
except ImportError:
    RICH_AVAILABLE = False
    logger.info("Rich library not available. Using plain text output.")

# === Security Configuration ===
# High iteration count prevents rainbow table attacks and ensures thorough entropy mixing
PBKDF2_ITERATIONS = 888_888  # Consistent with other tools in the suite
DERIVED_KEY_LENGTH = 32  # 256 bits

# === Elder Futhark Rune Database ===
# The 24 runes of the Elder Futhark, including meanings and reversibility.
RUNE_DATABASE: List[Dict[str, Any]] = [
    {"symbol": "ᚠ", "name": "Fehu", "phonetic": "f", "reversible": True,
     "upright_meaning": "Wealth, abundance, prosperity, foresight.",
     "reversed_meaning": "Loss of property, failure, greed, burnout."},
    {"symbol": "ᚢ", "name": "Uruz", "phonetic": "u", "reversible": True,
     "upright_meaning": "Strength, determination, health, courage.",
     "reversed_meaning": "Weakness, obsession, misdirected force, sickness."},
    {"symbol": "ᚦ", "name": "Thurisaz", "phonetic": "th", "reversible": True,
     "upright_meaning": "Reaction, defense, conflict, catharsis.",
     "reversed_meaning": "Danger, defenselessness, compulsion, betrayal."},
    {"symbol": "ᚨ", "name": "Ansuz", "phonetic": "a", "reversible": True,
     "upright_meaning": "Communication, signals, inspiration, divine messages.",
     "reversed_meaning": "Misunderstanding, deceit, manipulation, vanity."},
    {"symbol": "ᚱ", "name": "Raido", "phonetic": "r", "reversible": True,
     "upright_meaning": "Journey, change, movement, perspective.",
     "reversed_meaning": "Crisis, rigidity, stasis, injustice."},
    {"symbol": "ᚲ", "name": "Kenaz", "phonetic": "k", "reversible": True,
     "upright_meaning": "Vision, creativity, knowledge, enlightenment.",
     "reversed_meaning": "Disease, breakup, instability, lack of creativity."},
    {"symbol": "ᚷ", "name": "Gebo", "phonetic": "g", "reversible": False,
     "upright_meaning": "Gifts, partnership, generosity, balance.",
     "reversed_meaning": "Gifts, partnership, generosity, balance."},
    {"symbol": "ᚹ", "name": "Wunjo", "phonetic": "w", "reversible": True,
     "upright_meaning": "Joy, comfort, pleasure, fellowship.",
     "reversed_meaning": "Sorrow, strife, alienation, intoxication."},
    {"symbol": "ᚺ", "name": "Hagalaz", "phonetic": "h", "reversible": False,
     "upright_meaning": "Disruption, radical change, destructive natural forces.",
     "reversed_meaning": "Disruption, radical change, destructive natural forces."},
    {"symbol": "ᚾ", "name": "Nauthiz", "phonetic": "n", "reversible": True,
     "upright_meaning": "Need, constraint, distress, deliverance.",
     "reversed_meaning": "Toil, drudgery, want, deprivation."},
    {"symbol": "ᛁ", "name": "Isa", "phonetic": "i", "reversible": False,
     "upright_meaning": "Stasis, challenge, introspection, waiting.",
     "reversed_meaning": "Stasis, challenge, introspection, waiting."},
    {"symbol": "ᛃ", "name": "Jera", "phonetic": "j", "reversible": False,
     "upright_meaning": "Harvest, cycles, reward, fruition of efforts.",
     "reversed_meaning": "Harvest, cycles, reward, fruition of efforts."},
    {"symbol": "ᛇ", "name": "Eihwaz", "phonetic": "ei", "reversible": False,
     "upright_meaning": "Defense, endurance, connection between worlds.",
     "reversed_meaning": "Defense, endurance, connection between worlds."},
    {"symbol": "ᛈ", "name": "Perthro", "phonetic": "p", "reversible": True,
     "upright_meaning": "Mystery, fate, chance, occult abilities.",
     "reversed_meaning": "Stagnation, loneliness, addiction, secrets revealed."},
    {"symbol": "ᛉ", "name": "Algiz", "phonetic": "z", "reversible": True,
     "upright_meaning": "Protection, higher self, divinity, sanctuary.",
     "reversed_meaning": "Hidden danger, warning, loss of divine link."},
    {"symbol": "ᛊ", "name": "Sowilo", "phonetic": "s", "reversible": False,
     "upright_meaning": "Success, goals achieved, honor, wholeness.",
     "reversed_meaning": "Success, goals achieved, honor, wholeness."},
    {"symbol": "ᛏ", "name": "Tiwaz", "phonetic": "t", "reversible": True,
     "upright_meaning": "Honor, justice, leadership, victory.",
     "reversed_meaning": "Injustice, imbalance, conflict, failure in competition."},
    {"symbol": "ᛒ", "name": "Berkano", "phonetic": "b", "reversible": True,
     "upright_meaning": "Birth, fertility, new beginnings, growth.",
     "reversed_meaning": "Family problems, domestic strife, sterility."},
    {"symbol": "ᛖ", "name": "Ehwaz", "phonetic": "e", "reversible": True,
     "upright_meaning": "Movement, progress, teamwork, trust.",
     "reversed_meaning": "Restlessness, disharmony, betrayal, lack of progress."},
    {"symbol": "ᛗ", "name": "Mannaz", "phonetic": "m", "reversible": True,
     "upright_meaning": "The Self, humanity, awareness, social order.",
     "reversed_meaning": "Depression, mortality, self-delusion, isolation."},
    {"symbol": "ᛚ", "name": "Laguz", "phonetic": "l", "reversible": True,
     "upright_meaning": "Flow, water, intuition, the subconscious.",
     "reversed_meaning": "Fear, circular thinking, avoidance, withering."},
    {"symbol": "ᛜ", "name": "Ingwaz", "phonetic": "ng", "reversible": False,
     "upright_meaning": "Gestation, internal growth, potential energy.",
     "reversed_meaning": "Gestation, internal growth, potential energy."},
    {"symbol": "ᛞ", "name": "Dagaz", "phonetic": "d", "reversible": False,
     "upright_meaning": "Breakthrough, awakening, clarity, hope.",
     "reversed_meaning": "Breakthrough, awakening, clarity, hope."},
    {"symbol": "ᛟ", "name": "Othala", "phonetic": "o", "reversible": True,
     "upright_meaning": "Inheritance, heritage, home, spiritual legacy.",
     "reversed_meaning": "Lack of custom, bad karma, prejudice, poverty."}
]

# === Helper Functions & Classes ===
def secure_hash(data: bytes, salt: bytes, iterations: int = PBKDF2_ITERATIONS) -> bytes:
    """Generate cryptographically secure hash using PBKDF2."""
    return hashlib.pbkdf2_hmac('sha256', data, salt, iterations, DERIVED_KEY_LENGTH)

@dataclass
class DrawnRune:
    """Represents a single rune drawn in a reading."""
    rune_info: Dict[str, Any]
    is_reversed: bool

@dataclass
class RuneReading:
    """Represents a complete rune reading result."""
    query: str
    timestamp: str
    authentication: str
    drawn_runes: List[DrawnRune]

class RuneCaster:
    """Main rune divination system."""
    
    def cast(self, query: str, num_runes: int) -> RuneReading:
        """
        Perform a complete rune casting for the given query.
        This process simulates drawing runes from a bag without replacement.
        """
        if not (1 <= num_runes <= len(RUNE_DATABASE)):
            raise ValueError(f"Number of runes must be between 1 and {len(RUNE_DATABASE)}.")
            
        timestamp = datetime.now(timezone.utc).isoformat(timespec='seconds')
        seed_material = f"{query}|{timestamp}".encode('utf-8')
        base_seed = hashlib.sha256(seed_material).digest()
        
        # Authentication hash (first 8 hex chars)
        auth_hash = secure_hash(base_seed, b"rune-auth")
        auth_string = auth_hash.hex()[:8].upper()
        
        available_runes = list(RUNE_DATABASE)
        drawn_runes_list = []
        
        for i in range(num_runes):
            # Derive entropy for selecting a rune from the remaining pool
            selection_salt = f"rune-select-{i}".encode('utf-8')
            selection_hash = secure_hash(base_seed, selection_salt)
            selection_index = int.from_bytes(selection_hash, 'big') % len(available_runes)
            
            # Select and remove the rune to prevent re-drawing
            selected_rune = available_runes.pop(selection_index)
            
            # Derive entropy for determining orientation (upright/reversed)
            orientation_salt = f"rune-orient-{selected_rune['name']}-{i}".encode('utf-8')
            orientation_hash = secure_hash(base_seed, orientation_salt)
            
            # A single bit is enough to determine reversal
            is_reversed = (orientation_hash[0] & 1) == 1
            
            # IMPORTANT: Override reversal if the rune is not reversible
            if not selected_rune['reversible']:
                is_reversed = False
                
            drawn_runes_list.append(DrawnRune(
                rune_info=selected_rune,
                is_reversed=is_reversed
            ))
            
        return RuneReading(
            query=query,
            timestamp=timestamp,
            authentication=auth_string,
            drawn_runes=drawn_runes_list
        )

# === Display Functions ===
def display_reading(reading: RuneReading):
    """Display the complete rune reading."""
    
    # Define position labels for common spreads
    num_drawn = len(reading.drawn_runes)
    position_labels = {
        1: ["The Situation"],
        3: ["Past", "Present", "Future"],
        5: ["Situation", "Challenge", "Guidance", "Potential", "Outcome"]
    }
    labels = position_labels.get(num_drawn, [f"Rune #{i+1}" for i in range(num_drawn)])

    if RICH_AVAILABLE:
        console.rule(f"[bold cyan]ᛟ RUNE DIVINATION ᛟ[/bold cyan]")
        console.print(f"[dim]Query:[/dim] {reading.query}")
        console.print(f"[dim]Time:[/dim] {reading.timestamp}")
        console.print(f"[dim]Auth:[/dim] [bold green]{reading.authentication}[/bold green]")
        console.print()

        for i, drawn_rune in enumerate(reading.drawn_runes):
            rune = drawn_rune.rune_info
            
            orientation_text = Text("Reversed", style="bold red") if drawn_rune.is_reversed else Text("Upright", style="bold green")
            meaning = rune['reversed_meaning'] if drawn_rune.is_reversed else rune['upright_meaning']
            
            panel_content = Text()
            panel_content.append(f"{rune['symbol']} {rune['name']} ({rune['phonetic'].upper()})\n", style="bold white")
            panel_content.append("Orientation: ", style="dim")
            panel_content.append(orientation_text)
            panel_content.append("\nMeaning: ", style="dim")
            panel_content.append(meaning)

            title = f"[bold]{labels[i]}[/bold]" if i < len(labels) else f"[bold]Rune #{i+1}[/bold]"
            console.print(Panel(panel_content, title=title, border_style="cyan", expand=False))
            
    else: # Plain text output
        print("\n" + "="*60)
        print("RUNE DIVINATION")
        print("="*60)
        print(f"Query: {reading.query}")
        print(f"Time: {reading.timestamp}")
        print(f"Auth: {reading.authentication}")

        for i, drawn_rune in enumerate(reading.drawn_runes):
            rune = drawn_rune.rune_info
            orientation = "Reversed" if drawn_rune.is_reversed else "Upright"
            meaning = rune['reversed_meaning'] if drawn_rune.is_reversed else rune['upright_meaning']
            label = labels[i] if i < len(labels) else f"Rune #{i+1}"
            
            print("\n" + "---" * 10)
            print(f"Position: {label}")
            print(f"Rune: {rune['symbol']} {rune['name']} ({rune['phonetic'].upper()})")
            print(f"Orientation: {orientation}")
            print(f"Meaning: {meaning}")
        print("\n" + "="*60)

def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        '-q', '--query',
        required=True,
        help='Your question or situation for the runes'
    )
    parser.add_argument(
        '-n', '--number',
        type=int,
        default=3,
        choices=[1, 3, 5],
        help='Number of runes to cast (1, 3, or 5). Default is 3 (Nornir cast).'
    )
    parser.add_argument(
        '--save',
        help='Save the detailed reading to a JSON file (e.g., reading.json or readings.jsonl)'
    )
    args = parser.parse_args()

    caster = RuneCaster()
    
    if RICH_AVAILABLE:
        with console.status("[bold cyan]Casting the runes...[/bold cyan]", spinner="dots"):
            reading = caster.cast(args.query, args.number)
    else:
        print("Casting the runes...", end="", flush=True)
        reading = caster.cast(args.query, args.number)
        print(" done.")
        
    display_reading(reading)

    if args.save:
        try:
            # Use a custom serializer to handle dataclasses
            class CustomEncoder(json.JSONEncoder):
                def default(self, o):
                    if isinstance(o, (DrawnRune, RuneReading)):
                        return asdict(o)
                    return super().default(o)

            save_path = Path(args.save)
            save_data = asdict(reading)
            
            if save_path.suffix.lower() == '.jsonl':
                # Append mode for JSONL
                with open(save_path, 'a', encoding='utf-8') as f:
                    f.write(json.dumps(save_data, ensure_ascii=False, cls=CustomEncoder) + '\n')
            else:
                # Regular JSON
                with open(save_path, 'w', encoding='utf-8') as f:
                    json.dump(save_data, f, ensure_ascii=False, indent=2, cls=CustomEncoder)

            output_msg = f"✓ Reading saved to {save_path}"
            if RICH_AVAILABLE:
                console.print(f"\n[green]{output_msg}[/green]")
            else:
                print(f"\n{output_msg}")
                
        except Exception as e:
            logger.error(f"Failed to save reading: {e}")

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\nDivination cancelled.")
        sys.exit(0)
    except Exception as e:
        logger.error(f"An unexpected error occurred: {e}")
        sys.exit(1)