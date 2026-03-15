"""
Trio Card Game Engine

Official rules implementation with SIMPLE and SPICY modes.

A trio = 3 identical cards
- Reveal cards one by one from middle or players' hands (lowest/highest only)
- Stop when you reveal 3 matching (win trio) or 2 different (fail, return cards)
- Win conditions vary by mode
"""

import random
import string
import asyncio
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Tuple
from fastapi import WebSocket
from datetime import datetime
from enum import Enum
import json


class GameMode(Enum):
    SIMPLE = "simple"
    SPICY = "spicy"


@dataclass
class Card:
    """A Trio card with a number (1-12)."""
    id: int
    number: int
    
    def to_dict(self, face_up: bool = True):
        return {
            "id": self.id,
            "number": self.number if face_up else None,
            "face_up": face_up
        }


@dataclass
class Player:
    """A player in the game."""
    id: str
    name: str
    hand: List[Card] = field(default_factory=list)  # Sorted by number
    trios: List[List[Card]] = field(default_factory=list)  # Collected trios
    connected: bool = True
    websocket: Optional[WebSocket] = None
    is_cpu: bool = False
    cpu_difficulty: str = "medium"  # "easy", "medium", "hard"
    
    def sort_hand(self):
        """Sort hand by card number."""
        self.hand.sort(key=lambda c: c.number)
    
    def get_lowest(self) -> Optional[Card]:
        """Get lowest card (first after sorting)."""
        return self.hand[0] if self.hand else None
    
    def get_highest(self) -> Optional[Card]:
        """Get highest card (last after sorting)."""
        return self.hand[-1] if self.hand else None
    
    def remove_card(self, card_id: int) -> Optional[Card]:
        """Remove and return a card by ID."""
        for i, card in enumerate(self.hand):
            if card.id == card_id:
                return self.hand.pop(i)
        return None
    
    def to_public_dict(self):
        """Public info visible to all players."""
        return {
            "id": self.id,
            "name": self.name,
            "card_count": len(self.hand),
            "trio_count": len(self.trios),
            "trios": [[c.number for c in trio] for trio in self.trios],
            "connected": self.connected,
            "is_cpu": self.is_cpu,
        }
    
    def to_private_dict(self):
        """Private info visible only to this player."""
        return {
            "hand": [c.to_dict() for c in self.hand],
            "lowest": self.get_lowest().number if self.get_lowest() else None,
            "highest": self.get_highest().number if self.get_highest() else None,
        }


@dataclass
class RevealedCard:
    """A card that has been revealed during a turn."""
    card: Card
    source: str  # "middle" or player_id
    source_name: str  # "Middle" or player name
    position: Optional[str] = None  # "lowest", "highest", or None for middle


@dataclass
class GameRoom:
    """A Trio game room."""
    id: str
    name: str
    mode: GameMode = GameMode.SIMPLE
    players: Dict[str, Player] = field(default_factory=dict)
    player_order: List[str] = field(default_factory=list)
    
    # Middle cards
    middle_cards: List[Card] = field(default_factory=list)
    middle_face_up: Dict[int, bool] = field(default_factory=dict)  # card_id -> is_face_up
    
    # Current turn state
    current_turn_index: int = 0
    revealed_this_turn: List[RevealedCard] = field(default_factory=list)

    # Pending "seen" acknowledgements (set of player_ids)
    acks_pending: set = field(default_factory=set)

    # Pending trio data (waiting for acks before collecting)
    pending_trio: Optional[dict] = None
    
    # Game state
    state: str = "waiting"  # waiting, playing, finished
    winner: Optional[str] = None
    winner_reason: str = ""
    
    created_at: datetime = field(default_factory=datetime.now)
    max_players: int = 6
    min_players: int = 3
    
    cpu_memory: Dict[int, int] = field(default_factory=dict)  # card_id -> number

    # Connected numbers for SPICY mode (which numbers connect to which)
    # In Trio, connected numbers are shown in card corners
    CONNECTIONS = {
        1: [6, 8],
        2: [5, 9],
        3: [4, 10],
        4: [3, 11],
        5: [2, 12],
        6: [1],
        7: [],
        8: [1],
        9: [2],
        10: [3],
        11: [4],
        12: [5]
    }
    
    @property
    def current_player_id(self) -> Optional[str]:
        if self.player_order and self.state == "playing":
            return self.player_order[self.current_turn_index % len(self.player_order)]
        return None
    
    @property
    def current_player(self) -> Optional[Player]:
        pid = self.current_player_id
        return self.players.get(pid) if pid else None
    
    def get_cards_per_player(self) -> Tuple[int, int]:
        """Return (cards_per_player, cards_in_middle) based on player count."""
        player_count = len(self.players)
        distribution = {
            3: (9, 9),
            4: (7, 8),
            5: (6, 6),
            6: (5, 6),
        }
        return distribution.get(player_count, (5, 6))
    
    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "mode": self.mode.value,
            "player_count": len(self.players),
            "max_players": self.max_players,
            "min_players": self.min_players,
            "state": self.state,
            "players": (
                [self.players[pid].to_public_dict() for pid in self.player_order if pid in self.players]
                if self.player_order else
                [p.to_public_dict() for p in self.players.values()]
            ),
            "current_player": self.current_player.name if self.current_player else None,
            "current_player_id": self.current_player_id,
        }


class TrioGameManager:
    """Manages all Trio game rooms and WebSocket connections."""
    
    def __init__(self):
        self.rooms: Dict[str, GameRoom] = {}
        self.player_rooms: Dict[str, str] = {}  # player_id -> room_id
    
    def generate_room_id(self) -> str:
        """Generate a short, readable room code."""
        return ''.join(random.choices(string.ascii_uppercase + string.digits, k=5))
    
    def generate_player_id(self) -> str:
        """Generate unique player ID."""
        return ''.join(random.choices(string.ascii_lowercase + string.digits, k=8))
    
    def create_deck(self) -> List[Card]:
        """
        Create the Trio deck.
        36 cards total: 3 copies of each number 1-12
        """
        deck = []
        card_id = 0
        for number in range(1, 13):  # 1-12
            for _ in range(3):  # 3 copies each
                deck.append(Card(id=card_id, number=number))
                card_id += 1
        
        random.shuffle(deck)
        return deck
    
    def create_room(self, room_name: str, mode: str = "simple") -> GameRoom:
        """Create a new game room."""
        room_id = self.generate_room_id()
        game_mode = GameMode.SPICY if mode.lower() == "spicy" else GameMode.SIMPLE
        room = GameRoom(id=room_id, name=room_name, mode=game_mode)
        self.rooms[room_id] = room
        return room
    
    def get_room(self, room_id: str) -> Optional[GameRoom]:
        """Get a room by ID."""
        return self.rooms.get(room_id)
    
    def list_rooms(self) -> List[dict]:
        """List all available rooms."""
        return [
            room.to_dict() 
            for room in self.rooms.values() 
            if room.state == "waiting" and len(room.players) < room.max_players
        ]
    
    async def connect(self, websocket: WebSocket, room_id: str, player_name: str) -> Optional[str]:
        """Player joins a room. Returns player_id or None if failed."""
        room = self.get_room(room_id)
        if not room:
            await websocket.send_json({"type": "error", "message": "Room not found"})
            return None
        
        if len(room.players) >= room.max_players:
            await websocket.send_json({"type": "error", "message": "Room is full"})
            return None
        
        if room.state != "waiting":
            await websocket.send_json({"type": "error", "message": "Game already in progress"})
            return None
        
        # Create player
        player_id = self.generate_player_id()
        player = Player(id=player_id, name=player_name, websocket=websocket)
        room.players[player_id] = player
        self.player_rooms[player_id] = room_id
        
        # Notify all players
        await self.broadcast(room_id, {
            "type": "player_joined",
            "player": player.to_public_dict(),
            "room": room.to_dict(),
        })
        
        # Send welcome message to new player
        await websocket.send_json({
            "type": "welcome",
            "player_id": player_id,
            "room": room.to_dict()
        })
        
        return player_id
    
    async def disconnect(self, player_id: str):
        """Handle player disconnect."""
        room_id = self.player_rooms.get(player_id)
        if not room_id:
            return
        
        room = self.get_room(room_id)
        if not room:
            return
        
        player = room.players.get(player_id)
        if player:
            player.connected = False

            await self.broadcast(room_id, {
                "type": "player_disconnected",
                "player_id": player_id,
                "player_name": player.name,
                "room": room.to_dict()
            }, exclude={player_id})

            if player_id in room.acks_pending:
                room.acks_pending.discard(player_id)
                await self.broadcast(room_id, {
                    "type": "ack_update",
                    "acks_pending": list(room.acks_pending),
                }, exclude={player_id})
                if not room.acks_pending:
                    if room.pending_trio:
                        await self.finalize_trio(room_id)
                    else:
                        await self.return_revealed_cards(room_id)
                        await self.next_turn(room_id)
            
            # If game hasn't started, remove player
            if room.state == "waiting":
                del room.players[player_id]
                del self.player_rooms[player_id]
                
                if len(room.players) == 0:
                    del self.rooms[room_id]
    
    async def broadcast(self, room_id: str, message: dict, exclude: Set[str] = None):
        """Send message to all players in room."""
        exclude = exclude or set()
        room = self.get_room(room_id)
        if not room:
            return
        
        for player_id, player in room.players.items():
            if player_id not in exclude and player.connected and not player.is_cpu:
                try:
                    await player.websocket.send_json(message)
                except:
                    player.connected = False
    
    async def send_to_player(self, room_id: str, player_id: str, message: dict):
        """Send private message to one player."""
        room = self.get_room(room_id)
        if room and player_id in room.players:
            player = room.players[player_id]
            if player.is_cpu:
                return
            if player.connected:
                try:
                    await player.websocket.send_json(message)
                except:
                    player.connected = False
    
    async def set_game_mode(self, room_id: str, player_id: str, mode: str):
        """Set the game mode (only before game starts)."""
        room = self.get_room(room_id)
        if not room or room.state != "waiting":
            return
        
        room.mode = GameMode.SPICY if mode.lower() == "spicy" else GameMode.SIMPLE
        
        await self.broadcast(room_id, {
            "type": "mode_changed",
            "mode": room.mode.value,
            "room": room.to_dict()
        })
    
    async def start_game(self, room_id: str, player_id: str):
        """Start the game."""
        room = self.get_room(room_id)
        if not room:
            return
        
        if len(room.players) < room.min_players:
            await self.send_to_player(room_id, player_id, {
                "type": "error",
                "message": f"Need at least {room.min_players} players to start"
            })
            return
        
        # Initialize game
        room.state = "playing"
        deck = self.create_deck()
        
        # Set up player order
        room.player_order = list(room.players.keys())
        random.shuffle(room.player_order)
        room.current_turn_index = 0
        
        # Deal cards
        cards_per_player, cards_in_middle = room.get_cards_per_player()
        
        for pid in room.players:
            player = room.players[pid]
            player.hand = deck[:cards_per_player]
            deck = deck[cards_per_player:]
            player.sort_hand()
        
        # Remaining cards go to middle
        room.middle_cards = deck[:cards_in_middle]
        room.middle_face_up = {card.id: False for card in room.middle_cards}
        
        # Notify all players
        await self.broadcast(room_id, {
            "type": "game_started",
            "mode": room.mode.value,
            "turn_order": [room.players[pid].name for pid in room.player_order],
            "current_player": room.current_player.name,
            "current_player_id": room.current_player_id,
            "middle_card_count": len(room.middle_cards),
            "room": room.to_dict(),
        })
        
        # Send each player their private hand
        for pid, player in room.players.items():
            await self.send_to_player(room_id, pid, {
                "type": "your_hand",
                "hand": player.to_private_dict(),
            })
        
        # Notify whose turn FIRST (so isMyTurn is set before game_state renders buttons)
        await self.send_to_player(room_id, room.current_player_id, {
            "type": "your_turn",
            "message": "It's your turn! Reveal cards to find a trio."
        })

        # THEN send initial game state (buttons will now be enabled for first player)
        await self.send_game_state(room_id)

        # Schedule CPU turn if first player is CPU
        if room.current_player and room.current_player.is_cpu:
            asyncio.create_task(self.cpu_take_turn(room_id, room.current_player_id))

        # Fire-and-forget commentary
        player_names = ", ".join(room.players[pid].name for pid in room.player_order)
        asyncio.create_task(_fire_commentary(self, room_id, "game_start", {"players": player_names}))
    
    async def send_game_state(self, room_id: str):
        """Send current game state to all players."""
        room = self.get_room(room_id)
        if not room:
            return
        
        # Build middle cards state (showing which are face up, taken, or face down)
        middle_state = []
        face_down_count = 0
        for card in room.middle_cards:
            card_state = room.middle_face_up.get(card.id, False)
            if card_state == "taken":
                # Card was used in a trio - empty space
                middle_state.append({
                    "id": card.id,
                    "number": None,
                    "face_up": False,
                    "taken": True
                })
            elif card_state:
                # Face up (revealed this turn)
                middle_state.append({
                    "id": card.id,
                    "number": card.number,
                    "face_up": True,
                    "taken": False
                })
            else:
                # Face down
                middle_state.append({
                    "id": card.id,
                    "number": None,
                    "face_up": False,
                    "taken": False
                })
                face_down_count += 1
        
        # Revealed cards this turn
        revealed = [{
            "card": r.card.to_dict(),
            "source": r.source_name,
            "source_id": r.source,
            "position": r.position
        } for r in room.revealed_this_turn]
        
        await self.broadcast(room_id, {
            "type": "game_state",
            "players": [room.players[pid].to_public_dict() for pid in room.player_order if pid in room.players],
            "middle_cards": middle_state,
            "middle_card_count": face_down_count,
            "revealed_this_turn": revealed,
            "current_player": room.current_player.name if room.current_player else None,
            "current_player_id": room.current_player_id,
        })
    
    async def reveal_from_middle(self, room_id: str, player_id: str, card_id: int):
        """Reveal a card from the middle."""
        room = self.get_room(room_id)
        if not room or room.state != "playing":
            return
        
        if room.current_player_id != player_id:
            await self.send_to_player(room_id, player_id, {
                "type": "error",
                "message": "It's not your turn!"
            })
            return
        
        # Find the card
        card = None
        for c in room.middle_cards:
            if c.id == card_id:
                card = c
                break
        
        if not card:
            await self.send_to_player(room_id, player_id, {
                "type": "error",
                "message": "Card not found in middle"
            })
            return
        
        if room.middle_face_up.get(card_id, False):
            await self.send_to_player(room_id, player_id, {
                "type": "error",
                "message": "This card is already face up"
            })
            return
        
        # Reveal the card
        room.middle_face_up[card_id] = True
        room.cpu_memory[card_id] = card.number

        # Add to revealed this turn
        room.revealed_this_turn.append(RevealedCard(
            card=card,
            source="middle",
            source_name="Middle"
        ))
        
        await self.broadcast(room_id, {
            "type": "card_revealed",
            "card": card.to_dict(),
            "source": "Middle",
            "position": None,
            "revealed_by": room.current_player.name,
            "show_to_all": True,
        })
        
        # Check turn result
        await self.check_reveal_result(room_id)
    
    async def reveal_from_player(self, room_id: str, player_id: str, target_player_id: str, position: str):
        """Reveal lowest or highest card from a player's hand."""
        room = self.get_room(room_id)
        if not room or room.state != "playing":
            return
        
        if room.current_player_id != player_id:
            await self.send_to_player(room_id, player_id, {
                "type": "error",
                "message": "It's not your turn!"
            })
            return
        
        if position not in ["lowest", "highest"]:
            await self.send_to_player(room_id, player_id, {
                "type": "error",
                "message": "Must reveal 'lowest' or 'highest'"
            })
            return
        
        target_player = room.players.get(target_player_id)
        if not target_player:
            await self.send_to_player(room_id, player_id, {
                "type": "error",
                "message": "Player not found"
            })
            return
        
        if not target_player.hand:
            await self.send_to_player(room_id, player_id, {
                "type": "error",
                "message": f"{target_player.name} has no cards"
            })
            return
        
        # Get the card
        card = target_player.get_lowest() if position == "lowest" else target_player.get_highest()

        # Remove from hand
        target_player.remove_card(card.id)
        room.cpu_memory[card.id] = card.number

        # Add to revealed this turn
        room.revealed_this_turn.append(RevealedCard(
            card=card,
            source=target_player_id,
            source_name=target_player.name,
            position=position
        ))
        
        await self.broadcast(room_id, {
            "type": "card_revealed",
            "card": card.to_dict(),
            "source": target_player.name,
            "source_id": target_player_id,
            "position": position,
            "revealed_by": room.current_player.name,
            "show_to_all": True,
        })
        
        # Update target player's hand view
        await self.send_to_player(room_id, target_player_id, {
            "type": "your_hand",
            "hand": target_player.to_private_dict(),
        })
        
        # Send updated player info
        await self.send_game_state(room_id)
        
        # Check turn result
        await self.check_reveal_result(room_id)
    
    async def check_reveal_result(self, room_id: str):
        """Check if the current reveal sequence results in trio or fail."""
        room = self.get_room(room_id)
        if not room:
            return
        
        revealed = room.revealed_this_turn
        if len(revealed) < 2:
            # Not enough cards to determine outcome yet
            await self.send_game_state(room_id)
            return
        
        # Get all revealed numbers
        numbers = [r.card.number for r in revealed]
        
        # Check for trio (3 identical)
        if len(revealed) >= 3:
            if numbers[-1] == numbers[-2] == numbers[-3]:
                # TRIO FOUND! Send game state first so everyone sees all 3 revealed cards
                await self.send_game_state(room_id)
                await self.complete_trio(room_id)
                return
        
        # Check for fail (2 different numbers)
        if numbers[-1] != numbers[-2]:
            # IMPORTANT: Send game state FIRST so everyone can see the mismatched card!
            await self.send_game_state(room_id)
            # Then fail the turn (which has a delay before returning cards)
            await self.fail_turn(room_id)
            return
        
        # Same numbers so far but not 3 yet - continue
        await self.broadcast(room_id, {
            "type": "reveal_match",
            "message": f"Match! ({numbers[-1]}) Keep revealing...",
            "count": len(revealed)
        })
        
        await self.send_game_state(room_id)
    
    async def complete_trio(self, room_id: str):
        """Current player successfully completed a trio - wait for acks before collecting."""
        room = self.get_room(room_id)
        if not room:
            return

        player = room.current_player
        trio_cards = [r.card for r in room.revealed_this_turn[-3:]]
        trio_number = trio_cards[0].number

        # Store pending trio info but DON'T collect yet
        room.pending_trio = {
            "player_id": player.id,
            "cards": trio_cards,
            "number": trio_number,
            "revealed": room.revealed_this_turn[-3:],
        }

        # Set acks (same as fail_turn)
        room.acks_pending = {pid for pid, p in room.players.items() if p.connected}

        # CPU players auto-ACK immediately
        for pid in list(room.acks_pending):
            if room.players[pid].is_cpu:
                room.acks_pending.discard(pid)

        await self.broadcast(room_id, {
            "type": "trio_complete",
            "player": player.name,
            "player_id": player.id,
            "trio_number": trio_number,
            "message": f"🎉 {player.name} got a trio of {trio_number}s!",
            "acks_required": True,
            "acks_pending": list(room.acks_pending),
        })

        # Fire-and-forget commentary
        asyncio.create_task(_fire_commentary(self, room_id, "trio_claimed", {
            "player": player.name,
            "cards": f"{trio_number}, {trio_number}, {trio_number}",
        }))

        # If all acks handled (only CPU players), proceed immediately
        if not room.acks_pending:
            await self.finalize_trio(room_id)

    async def finalize_trio(self, room_id: str):
        """Finalize trio collection after all acks received."""
        room = self.get_room(room_id)
        if not room or not room.pending_trio:
            return

        pending = room.pending_trio
        room.pending_trio = None
        player = room.players[pending["player_id"]]

        # Collect trio
        player.trios.append(pending["cards"])

        # Mark middle cards as taken
        for r in pending["revealed"]:
            if r.source == "middle":
                room.middle_face_up[r.card.id] = "taken"

        # Clear revealed
        room.revealed_this_turn = []

        # Update all hands
        for pid, p in room.players.items():
            await self.send_to_player(room_id, pid, {
                "type": "your_hand",
                "hand": p.to_private_dict(),
            })

        # Check win condition
        win = await self.check_win_condition(room_id, pending["player_id"])
        if not win:
            await self.next_turn(room_id)
    
    async def fail_turn(self, room_id: str):
        """Current player's turn failed - wait for all players to acknowledge before hiding cards."""
        room = self.get_room(room_id)
        if not room:
            return

        player = room.current_player
        room.acks_pending = {pid for pid, p in room.players.items() if p.connected}

        # CPU players auto-ACK immediately
        for pid in list(room.acks_pending):
            if room.players[pid].is_cpu:
                room.acks_pending.discard(pid)

        revealed_numbers = [str(r.card.number) for r in room.revealed_this_turn]
        await self.broadcast(room_id, {
            "type": "turn_failed",
            "player": player.name,
            "message": f"Different numbers! {player.name}'s turn ends.",
            "acks_required": True,
            "acks_pending": list(room.acks_pending),
        })

        # Fire-and-forget commentary
        asyncio.create_task(_fire_commentary(self, room_id, "trio_failed", {
            "player": player.name,
            "cards": ", ".join(revealed_numbers),
        }))

        # If all acks handled (only CPU players), proceed immediately
        if not room.acks_pending:
            await self.return_revealed_cards(room_id)
            await self.next_turn(room_id)
    
    async def return_revealed_cards(self, room_id: str):
        """Return all revealed cards to their sources."""
        room = self.get_room(room_id)
        if not room:
            return
        
        for revealed in room.revealed_this_turn:
            if revealed.source == "middle":
                # Flip back face down
                room.middle_face_up[revealed.card.id] = False
            else:
                # Return to player's hand
                player = room.players.get(revealed.source)
                if player:
                    player.hand.append(revealed.card)
                    player.sort_hand()
                    # Update their hand view
                    await self.send_to_player(room_id, revealed.source, {
                        "type": "your_hand",
                        "hand": player.to_private_dict(),
                    })
        
        # Clear revealed
        room.revealed_this_turn = []
        
        # Update game state
        await self.send_game_state(room_id)
    
    async def check_win_condition(self, room_id: str, player_id: str) -> bool:
        """Check if player has won. Returns True if game ended."""
        room = self.get_room(room_id)
        if not room:
            return False
        
        player = room.players[player_id]
        trios = player.trios
        
        # Check for 7-trio (instant win in both modes)
        for trio in trios:
            if all(c.number == 7 for c in trio):
                room.state = "finished"
                room.winner = player_id
                room.winner_reason = "7-trio"
                await self.announce_winner(room_id, player, "Got the legendary 7-7-7 trio! 🎰")
                return True
        
        if room.mode == GameMode.SIMPLE:
            # Win with 3 trios
            if len(trios) >= 3:
                room.state = "finished"
                room.winner = player_id
                room.winner_reason = "3_trios"
                await self.announce_winner(room_id, player, "Collected 3 trios!")
                return True
        
        else:  # SPICY mode
            # Win with 2 connected trios
            if len(trios) >= 2:
                trio_numbers = [trio[0].number for trio in trios]
                # Check if any two trios are connected
                for i, num1 in enumerate(trio_numbers):
                    for num2 in trio_numbers[i+1:]:
                        if num2 in room.CONNECTIONS.get(num1, []):
                            room.state = "finished"
                            room.winner = player_id
                            room.winner_reason = "connected_trios"
                            await self.announce_winner(room_id, player, 
                                f"Got 2 connected trios ({num1} ↔ {num2})! 🔗")
                            return True
        
        return False
    
    async def announce_winner(self, room_id: str, player: Player, reason: str):
        """Announce the winner."""
        room = self.get_room(room_id)
        if not room:
            return
        
        final_scores = [
            {"name": p.name, "trios": len(p.trios)}
            for p in sorted(room.players.values(), key=lambda x: len(x.trios), reverse=True)
        ]
        await self.broadcast(room_id, {
            "type": "game_over",
            "winner": player.name,
            "winner_id": player.id,
            "reason": reason,
            "message": f"🏆 {player.name} wins! {reason}",
            "final_scores": final_scores,
        })

        # Fire-and-forget commentary
        scores_str = ", ".join(f"{s['name']}: {s['trios']} trios" for s in final_scores)
        asyncio.create_task(_fire_commentary(self, room_id, "game_won", {
            "player": player.name,
            "scores": scores_str,
        }))
    
    async def next_turn(self, room_id: str):
        """Move to the next player's turn."""
        room = self.get_room(room_id)
        if not room:
            return
        
        room.current_turn_index = (room.current_turn_index + 1) % len(room.player_order)
        room.revealed_this_turn = []
        
        next_player = room.current_player
        
        await self.broadcast(room_id, {
            "type": "turn_changed",
            "current_player": next_player.name,
            "current_player_id": next_player.id
        })

        await self.send_to_player(room_id, next_player.id, {
            "type": "your_turn",
            "message": "It's your turn! Reveal cards to find a trio."
        })

        await self.send_game_state(room_id)

        if next_player.is_cpu:
            asyncio.create_task(self.cpu_take_turn(room_id, next_player.id))

    async def handle_seen_ack(self, room_id: str, player_id: str):
        """Handle a player's 'seen' acknowledgement after a failed turn or trio."""
        room = self.get_room(room_id)
        if not room or player_id not in room.acks_pending:
            return
        room.acks_pending.discard(player_id)
        await self.broadcast(room_id, {
            "type": "ack_update",
            "acks_pending": list(room.acks_pending),
        })
        if not room.acks_pending:
            if room.pending_trio:
                await self.finalize_trio(room_id)
            else:
                await self.return_revealed_cards(room_id)
                await self.next_turn(room_id)

    async def handle_action(self, room_id: str, player_id: str, data: dict):
        """Handle incoming player action."""
        action = data.get("action")
        
        if action == "set_mode":
            mode = data.get("mode", "simple")
            await self.set_game_mode(room_id, player_id, mode)
        
        elif action == "start_game":
            await self.start_game(room_id, player_id)
        
        elif action == "reveal_middle":
            card_id = data.get("card_id")
            if card_id is not None:
                room = self.get_room(room_id)
                if room and room.acks_pending:
                    return  # Ignore reveals while waiting for seen acks
                await self.reveal_from_middle(room_id, player_id, card_id)

        elif action == "reveal_player":
            target_id = data.get("target_player_id")
            position = data.get("position")  # "lowest" or "highest"
            if target_id and position:
                room = self.get_room(room_id)
                if room and room.acks_pending:
                    return  # Ignore reveals while waiting for seen acks
                await self.reveal_from_player(room_id, player_id, target_id, position)
        
        elif action == "seen_ack":
            await self.handle_seen_ack(room_id, player_id)

        elif action == "chat":
            message = data.get("message", "")
            room = self.get_room(room_id)
            if room:
                player = room.players.get(player_id)
                if player:
                    await self.broadcast(room_id, {
                        "type": "chat",
                        "player": player.name,
                        "message": message
                    })


    async def add_cpu_player(self, room_id: str, difficulty: str = "medium") -> Optional[Player]:
        """Add a CPU-controlled player to a waiting room."""
        room = self.get_room(room_id)
        if not room or room.state != "waiting":
            return None
        if len(room.players) >= room.max_players:
            return None

        difficulty = difficulty if difficulty in ("easy", "medium", "hard") else "medium"
        base_names = {"easy": "CPU (Easy)", "medium": "CPU (Medium)", "hard": "CPU (Hard)"}
        base_name = base_names[difficulty]
        name = base_name
        existing_names = {p.name for p in room.players.values()}
        counter = 2
        while name in existing_names:
            name = f"{base_name} #{counter}"
            counter += 1

        player_id = self.generate_player_id()
        player = Player(
            id=player_id,
            name=name,
            connected=True,
            is_cpu=True,
            cpu_difficulty=difficulty,
        )
        room.players[player_id] = player
        self.player_rooms[player_id] = room_id

        await self.broadcast(room_id, {
            "type": "player_joined",
            "player": player.to_public_dict(),
            "room": room.to_dict(),
        })
        return player

    async def cpu_take_turn(self, room_id: str, cpu_player_id: str):
        """CPU player autonomously takes their turn."""
        await asyncio.sleep(random.uniform(1.2, 2.5))

        room = self.get_room(room_id)
        if not room or room.state != "playing":
            return
        if room.current_player_id != cpu_player_id:
            return
        if room.acks_pending:
            return

        while True:
            room = self.get_room(room_id)
            if not room or room.state != "playing":
                return
            if room.current_player_id != cpu_player_id:
                return
            if room.acks_pending:
                return

            cpu_player = room.players.get(cpu_player_id)
            if not cpu_player:
                return

            action = self._cpu_choose_reveal(room, cpu_player)

            if action["type"] == "middle":
                await self.reveal_from_middle(room_id, cpu_player_id, action["card_id"])
            else:
                await self.reveal_from_player(room_id, cpu_player_id, action["target_id"], action["position"])

            # Check if turn is still ongoing after the reveal
            room = self.get_room(room_id)
            if not room or room.state != "playing":
                return
            if room.current_player_id != cpu_player_id:
                return
            if room.acks_pending:
                return

            # Still this CPU's turn — pause before next reveal
            await asyncio.sleep(random.uniform(0.8, 1.5))

    def _cpu_choose_reveal(self, room: "GameRoom", player: Player) -> dict:
        """Choose what the CPU player should reveal based on difficulty."""
        difficulty = player.cpu_difficulty
        if difficulty == "easy":
            return self._cpu_easy_choice(room)
        elif difficulty == "medium":
            return self._cpu_medium_choice(room)
        else:
            return self._cpu_hard_choice(room, player)

    def _cpu_easy_choice(self, room: "GameRoom") -> dict:
        """Easy: pure random reveal."""
        choices = []
        for card in room.middle_cards:
            if room.middle_face_up.get(card.id, False) is False:
                choices.append({"type": "middle", "card_id": card.id})
        for pid, p in room.players.items():
            if p.hand:
                choices.append({"type": "player", "target_id": pid, "position": "lowest"})
                choices.append({"type": "player", "target_id": pid, "position": "highest"})
        return random.choice(choices) if choices else {"type": "middle", "card_id": -1}

    def _cpu_medium_choice(self, room: "GameRoom") -> dict:
        """Medium: memory-based — target cards known to match already-revealed numbers."""
        revealed_numbers = [r.card.number for r in room.revealed_this_turn]
        if revealed_numbers:
            target_number = revealed_numbers[-1]
            # Check middle cards
            for card in room.middle_cards:
                if room.middle_face_up.get(card.id, False) is False:
                    if room.cpu_memory.get(card.id) == target_number:
                        return {"type": "middle", "card_id": card.id}
            # Check player cards
            for pid, p in room.players.items():
                if not p.hand:
                    continue
                lowest = p.get_lowest()
                if lowest and room.cpu_memory.get(lowest.id) == target_number:
                    return {"type": "player", "target_id": pid, "position": "lowest"}
                highest = p.get_highest()
                if highest and room.cpu_memory.get(highest.id) == target_number:
                    return {"type": "player", "target_id": pid, "position": "highest"}
        return self._cpu_easy_choice(room)

    def _cpu_hard_choice(self, room: "GameRoom", player: Player) -> dict:
        """Hard: strategic memory-based play with spicy-mode awareness.

        Rules:
        - Never reveal a card already known to mismatch the target number.
        - Never reveal an unknown card from a player already tapped this turn
          (avoids wasteful lowest→highest same-hand reveals).
        - When no card is revealed yet: prefer numbers connected to own trios
          (spicy) or numbers where we already know 2+ cards.
        - Fall back gracefully through tiers rather than making random moves.
        """
        from collections import Counter

        revealed = room.revealed_this_turn
        revealed_numbers = [r.card.number for r in revealed]
        # Players we've already drawn from this turn — don't pull unknown from them again
        tapped_players = {r.source for r in revealed if r.source != "middle"}

        if revealed_numbers:
            target = revealed_numbers[-1]

            # Tier 1: known card that matches target (any source)
            result = self._hard_find_known(room, target)
            if result:
                return result

            # Tier 2: unknown card, but NOT from a player we already tapped this turn
            result = self._hard_find_unknown(room, exclude_players=tapped_players)
            if result:
                return result

            # Tier 3: non-certain-fail card, still exclude tapped players
            result = self._hard_find_nonfail(room, target, exclude_players=tapped_players)
            if result:
                return result

            # Tier 4: last resort — ignore tapped-player restriction
            result = self._hard_find_nonfail(room, target)
            if result:
                return result

            return self._cpu_easy_choice(room)

        else:
            # No cards revealed yet — choose the best starting card

            # In spicy mode, prioritize numbers connected to own existing trios
            if room.mode == GameMode.SPICY and player.trios:
                wanted = set()
                for trio in player.trios:
                    wanted.update(room.CONNECTIONS.get(trio[0].number, []))
                for number in wanted:
                    result = self._hard_find_known(room, number)
                    if result:
                        return result

            # Find numbers where we already know 2+ face-down cards (near-complete trio)
            known_counts = Counter(
                room.cpu_memory.get(c.id)
                for c in room.middle_cards
                if room.middle_face_up.get(c.id, False) is False
                and c.id in room.cpu_memory
            )
            for pid, p in room.players.items():
                seen_ids = set()
                for card in [p.get_lowest(), p.get_highest()]:
                    if card and card.id not in seen_ids and card.id in room.cpu_memory:
                        known_counts[room.cpu_memory[card.id]] += 1
                        seen_ids.add(card.id)

            best_numbers = [n for n, c in known_counts.most_common() if c >= 2]
            for number in best_numbers:
                result = self._hard_find_known(room, number)
                if result:
                    return result

            # Otherwise reveal an unknown card to gain information
            result = self._hard_find_unknown(room)
            if result:
                return result

            return self._cpu_easy_choice(room)

    def _hard_find_known(self, room: "GameRoom", target_number: int) -> Optional[dict]:
        """Return a face-down card we know has exactly target_number, or None."""
        for card in room.middle_cards:
            if room.middle_face_up.get(card.id, False) is False:
                if room.cpu_memory.get(card.id) == target_number:
                    return {"type": "middle", "card_id": card.id}
        for pid, p in room.players.items():
            if not p.hand:
                continue
            lowest = p.get_lowest()
            if lowest and room.cpu_memory.get(lowest.id) == target_number:
                return {"type": "player", "target_id": pid, "position": "lowest"}
            highest = p.get_highest()
            if highest and (lowest is None or highest.id != lowest.id):
                if room.cpu_memory.get(highest.id) == target_number:
                    return {"type": "player", "target_id": pid, "position": "highest"}
        return None

    def _hard_find_unknown(self, room: "GameRoom", exclude_players: set = None) -> Optional[dict]:
        """Return a card whose number we do not yet know (pure information gain)."""
        exclude_players = exclude_players or set()
        choices = []
        for card in room.middle_cards:
            if room.middle_face_up.get(card.id, False) is False and card.id not in room.cpu_memory:
                choices.append({"type": "middle", "card_id": card.id})
        for pid, p in room.players.items():
            if pid in exclude_players or not p.hand:
                continue
            lowest = p.get_lowest()
            if lowest and lowest.id not in room.cpu_memory:
                choices.append({"type": "player", "target_id": pid, "position": "lowest"})
            highest = p.get_highest()
            if highest and (lowest is None or highest.id != lowest.id) and highest.id not in room.cpu_memory:
                choices.append({"type": "player", "target_id": pid, "position": "highest"})
        return random.choice(choices) if choices else None

    def _hard_find_nonfail(self, room: "GameRoom", target_number: int,
                           exclude_players: set = None) -> Optional[dict]:
        """Return any card that won't certainly mismatch target_number (unknown or matching)."""
        exclude_players = exclude_players or set()
        choices = []
        for card in room.middle_cards:
            if room.middle_face_up.get(card.id, False) is False:
                known = room.cpu_memory.get(card.id)
                if known is None or known == target_number:
                    choices.append({"type": "middle", "card_id": card.id})
        for pid, p in room.players.items():
            if pid in exclude_players or not p.hand:
                continue
            lowest = p.get_lowest()
            if lowest:
                known = room.cpu_memory.get(lowest.id)
                if known is None or known == target_number:
                    choices.append({"type": "player", "target_id": pid, "position": "lowest"})
            highest = p.get_highest()
            if highest and (lowest is None or highest.id != lowest.id):
                known = room.cpu_memory.get(highest.id)
                if known is None or known == target_number:
                    choices.append({"type": "player", "target_id": pid, "position": "highest"})
        return random.choice(choices) if choices else None


async def _fire_commentary(manager: "TrioGameManager", room_id: str, event_type: str, details: dict):
    """Fire-and-forget commentary broadcast. Never raises."""
    try:
        from .commentator import comment_on_game_event
        text = await comment_on_game_event(event_type, details)
        if text:
            await manager.broadcast(room_id, {"type": "commentary", "text": text})
    except Exception:
        pass


# Global game manager instance
game_manager = TrioGameManager()
