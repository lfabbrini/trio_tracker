# CPU Player Algorithm — Trio Tracker

## Overview

The CPU player is a probability-driven AI that plays the card game Trio optimally. It maintains a **memory of revealed cards**, builds a **card distribution census** each turn, and uses **Bayesian-style conditional probabilities** to maximize its chances of completing a trio.

There is a single difficulty level: **hard**. The CPU always plays optimally.

---

## Game Rules Recap

- The deck has cards numbered 1–12, with **3 copies of each number** (36 cards total).
- On your turn, you reveal cards one by one (from the middle pile or other players' lowest/highest card).
- A **trio** = 3 cards with the same number.
- After the first reveal, you must keep revealing until:
  - You reveal a **3rd matching card** → you win the trio.
  - You reveal a **card that doesn't match** → turn ends, all revealed cards returned face-down.
- **Special rule:** Number **7** = instant game win if collected as a trio.
- **Spicy mode** adds connections between numbers; collecting a trio gives bonus opportunities.

---

## Architecture

```
cpu_take_turn()
    └─> _cpu_choose_reveal()
            ├─> _build_card_census()         # Knowledge snapshot
            ├─> _get_accessible_positions()  # What can be revealed
            │
            ├─> [1st reveal] _choose_opening()
            │       └─> score each number 1-12
            │               └─> _calc_match_probability()
            │
            └─> [2nd+ reveal] _choose_continuation()
                    └─> sort candidates by probability
                            └─> _calc_match_probability()
```

---

## Step 1 — Memory (`cpu_memory`)

```python
cpu_memory: Dict[int, int]  # card_id -> card_number
```

Every time any card is revealed (by anyone), the CPU records it:

```
cpu_memory[card_id] = card_number
```

This gives the CPU **perfect recall** of all previously seen cards. The memory persists across turns — the CPU never forgets a card it has seen.

---

## Step 2 — Card Census (`_build_card_census`)

Before each decision, the CPU scans the full game state and builds a `CardCensus`:

| Field | Meaning |
|---|---|
| `collected[n]` | How many copies of number `n` are already in someone's completed trios |
| `located[n]` | How many copies of `n` the CPU **knows the exact position of** (via memory or own hand) |
| `unlocated[n]` | How many copies of `n` are still in play but at **unknown positions** |
| `total_unknown` | Total number of accessible cards whose identity the CPU doesn't know |

### Formula

$$\text{unlocated}(n) = \max\bigl(0,\ 3 - \text{collected}(n) - \text{located}(n)\bigr)$$

$$\text{total\_unknown} = \bigl|\{c \in \text{accessible} \mid c \notin \text{cpu\_memory}\}\bigr|$$

---

## Step 3 — Probability Engine (`_calc_match_probability`)

For any position `pos` and target number `n`, the CPU computes the probability that the card at that position equals `n`.

### Case 1: Known card

$$P(\text{pos} = n) = \begin{cases} 1.0 & \text{if known\_number} = n \\ 0.0 & \text{otherwise} \end{cases}$$

### Case 2: Unknown middle card

Middle cards are assumed to be uniformly distributed among all unlocated cards:

$$P(\text{middle pos} = n) = \frac{\text{unlocated}(n)}{\text{total\_unknown}}$$

### Case 3: Unknown player card (lowest or highest)

Player hands have an **ordering constraint**: the lowest card ≤ the highest card. The CPU uses the known bound to restrict the eligible range.

**For a `lowest` position** (card must be ≤ known highest `H`):

$$P(\text{lowest pos} = n) = \frac{\text{unlocated}(n)}{\displaystyle\sum_{k=1}^{H} \text{unlocated}(k)}, \quad \text{if } n \leq H, \text{ else } 0$$

**For a `highest` position** (card must be ≥ known lowest `L`):

$$P(\text{highest pos} = n) = \frac{\text{unlocated}(n)}{\displaystyle\sum_{k=L}^{12} \text{unlocated}(k)}, \quad \text{if } n \geq L, \text{ else } 0$$

This is a **conditional uniform distribution** over the feasible range, accounting for what the CPU already knows about the hand ordering.

---

## Step 4 — Opening Move (`_choose_opening`)

On the **first reveal of a turn**, the CPU scores every number 1–12:

$$\text{score}(n) = \underbrace{\sum_{\text{pos} \in \text{known}} \mathbf{1}[\text{pos} = n]}_{\text{certain matches}} + \underbrace{\sum_{\text{pos} \in \text{unknown}} P(\text{pos} = n)}_{\text{expected matches}}$$

This gives the **expected number of accessible cards** that match number `n`.

### Multipliers

| Condition | Multiplier | Reason |
|---|---|---|
| Number is **connected** in Spicy mode | ×5.0 | Already have trios that chain to this number |
| Number is **7** | ×1.3 | Instant game win if collected |

$$\text{score\_final}(n) = \text{score}(n) \times M_{\text{spicy}}(n) \times M_7(n)$$

The CPU picks the number `n*` with the highest `score_final`, then selects the **best position** for that number using:

1. **Known card matching `n*`** — always preferred (probability = 1.0)
2. **Unknown middle card** with positive probability — second choice
3. **Unknown player card** with positive probability — fallback

---

## Step 5 — Continuation Move (`_choose_continuation`)

After the first card is revealed with number `target`, the CPU must find another card with the same number. It ranks all accessible positions by a composite score:

$$\text{rank}(\text{pos}) = \bigl(P(\text{pos} = \text{target}),\ \text{tapped\_penalty}(\text{pos}),\ \text{middle\_priority}(\text{pos})\bigr)$$

Sorted **descending** (highest probability first), with tiebreakers:

| Factor | Value | Reason |
|---|---|---|
| `tapped_penalty` | `-1` if player was already revealed this turn | Rules only allow one card per player hand per turn |
| `middle_priority` | `+1` if position is in the middle | Middle cards are neutral (no player penalty) |

If no candidate has positive probability (pure guess situation), the CPU picks a random unknown position as a last resort.

---

## Step 6 — Turn Loop (`cpu_take_turn`)

The CPU simulates human-like behavior with randomized delays:

```
Initial pause:     uniform(1.2, 2.5) seconds
Between reveals:   uniform(0.8, 1.5) seconds
```

After each reveal, the CPU re-evaluates the game state before deciding to continue.

---

## Example Walkthrough

**Setup:** 4 players (CPU, Alice, Bob, Charlie). 36 cards total — 7 cards each (4 × 7 = 28) → **8 cards in the middle** (face-down).

CPU's hand: `3, 3, 5, 7, 8, 11, 11, 12`

**Accessible positions the CPU can reveal:**
- 8 face-down middle cards
- Alice: lowest + highest = 2
- Bob: lowest + highest = 2
- Charlie: lowest + highest = 2

**Turn 0 — start of game, nothing revealed yet**

| Number | collected | located (CPU hand) | unlocated |
|--------|-----------|-------------------|-----------|
| 3  | 0 | 2 | **1** |
| 5  | 0 | 1 | **2** |
| 7  | 0 | 1 | **2** |
| 8  | 0 | 1 | **2** |
| 11 | 0 | 2 | **1** |
| 12 | 0 | 1 | **2** |
| 1  | 0 | 0 | **3** |
| 2  | 0 | 0 | **3** |
| 4  | 0 | 0 | **3** |
| 6  | 0 | 0 | **3** |
| 9  | 0 | 0 | **3** |
| 10 | 0 | 0 | **3** |

`total_unknown` = 8 (middle) + 6 (other players' accessible cards) = **14**

**Opening score for number 3** (CPU holds 2, one unknown somewhere):

$$\text{score}(3) = \underbrace{2}_{\text{in own hand}} + \underbrace{\frac{1}{14}}_{\text{P(any unknown = 3)}} \times 14 = 2 + 1.0 = 3.0$$

**Opening score for number 1** (CPU holds none, all 3 unknown):

$$\text{score}(1) = 0 + \frac{3}{14} \times 14 = 3.0$$

Both score 3.0 — but number 3 is **far safer**: the CPU already holds 2 guaranteed cards and only needs to find 1 more. Number 1 requires finding all 3 by luck.

**Now Alice takes her turn and reveals her lowest card: a 4.**

CPU logs: `cpu_memory[alice_lowest_id] = 4`

`located[4]` goes 0 → 1, `unlocated[4]` goes 3 → **2**, `total_unknown` drops 14 → **13**.

**CPU's turn — score for number 4** (Alice's lowest is a known 4):

$$\text{score}(4) = \underbrace{1}_{\text{Alice's known card}} + \underbrace{\frac{2}{13}}_{\text{P(any unknown = 4)}} \times 13 = 1 + 2.0 = 3.0$$

Still 3.0, but again: number 3 wins because the CPU already holds 2 of them — it only needs to find 1 out of 13 remaining unknowns, vs needing to find 2 out of 13 for number 4.

---

## Key Design Decisions

| Decision | Rationale |
|---|---|
| **Perfect memory** | CPU never forgets revealed cards — models an optimal human player |
| **Census rebuilt each turn** | Ensures accuracy after every state change (collected trios, new reveals) |
| **Ordered hand constraints** | Exploits known hand structure to improve probability estimates for player cards |
| **Expected value scoring** | Maximizes the probability of starting a turn on the best-possible number |
| **Spicy mode bonus ×5** | Strongly prioritizes completing trio chains, which is the dominant strategy in Spicy |
| **Number 7 bonus ×1.3** | Small nudge toward the instant-win card without completely dominating the strategy |
