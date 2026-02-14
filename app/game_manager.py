"""
Trio Card Game Engine

Official rules implementation with SIMPLE and SPICY modes.

A trio = 3 identical cards
- Reveal cards one by one from middle or players' hands (lowest/highest only)
- Stop when you reveal 3 matching (win trio) or 2 different (fail, return cards)
- Win conditions vary by mode
"""

import asyncio
import random
import string
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
    websocket: WebSocket
    hand: List[Card] = field(default_factory=list)  # Sorted by number
    trios: List[List[Card]] = field(default_factory=list)  # Collected trios
    connected: bool = True
    
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
            "connected": self.connected
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
    
    # Game state
    state: str = "waiting"  # waiting, playing, finished
    winner: Optional[str] = None
    winner_reason: str = ""
    
    created_at: datetime = field(default_factory=datetime.now)
    max_players: int = 6
    min_players: int = 3
    
    # Connected numbers for SPICY mode (which numbers connect to which)
    # In Trio, connected numbers are shown in card corners
    CONNECTIONS = {
        1: [2, 3],
        2: [1, 3, 4],
        3: [1, 2, 4, 5],
        4: [2, 3, 5, 6],
        5: [3, 4, 6, 7],
        6: [4, 5, 7, 8],
        7: [5, 6, 8, 9],
        8: [6, 7, 9, 10],
        9: [7, 8, 10, 11],
        10: [8, 9, 11, 12],
        11: [9, 10, 12],
        12: [10, 11]
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
            "players": [p.to_public_dict() for p in self.players.values()],
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
            "room": room.to_dict()
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
            if player_id not in exclude and player.connected:
                try:
                    await player.websocket.send_json(message)
                except:
                    player.connected = False
    
    async def send_to_player(self, room_id: str, player_id: str, message: dict):
        """Send private message to one player."""
        room = self.get_room(room_id)
        if room and player_id in room.players:
            player = room.players[player_id]
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
            "room": room.to_dict()
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
            "position": r.position
        } for r in room.revealed_this_turn]
        
        await self.broadcast(room_id, {
            "type": "game_state",
            "players": [p.to_public_dict() for p in room.players.values()],
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
            "show_to_all": True  # Middle cards are visible to all
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
            "show_to_all": True  # All revealed cards are visible to everyone
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
                # TRIO FOUND!
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
        """Current player successfully completed a trio."""
        room = self.get_room(room_id)
        if not room:
            return
        
        player = room.current_player
        trio_cards = [r.card for r in room.revealed_this_turn[-3:]]
        trio_number = trio_cards[0].number
        
        # Add trio to player's collection
        player.trios.append(trio_cards)
        
        # Mark trio cards as taken (but keep positions in middle)
        for r in room.revealed_this_turn[-3:]:
            if r.source == "middle":
                # Mark as taken instead of removing
                room.middle_face_up[r.card.id] = "taken"
        
        # Clear revealed (trio cards are collected, others were already removed from hands)
        room.revealed_this_turn = []
        
        await self.broadcast(room_id, {
            "type": "trio_complete",
            "player": player.name,
            "player_id": player.id,
            "trio_number": trio_number,
            "message": f"🎉 {player.name} got a trio of {trio_number}s!"
        })
        
        # Update all hands
        for pid, p in room.players.items():
            await self.send_to_player(room_id, pid, {
                "type": "your_hand",
                "hand": p.to_private_dict(),
            })
        
        # Check win condition
        win = await self.check_win_condition(room_id, player.id)
        
        if not win:
            # Same player continues their turn!
            await self.send_game_state(room_id)
            await self.send_to_player(room_id, room.current_player_id, {
                "type": "your_turn",
                "message": "Great trio! Continue your turn - find another!"
            })
    
    async def fail_turn(self, room_id: str):
        """Current player's turn failed - return all revealed cards."""
        room = self.get_room(room_id)
        if not room:
            return
        
        player = room.current_player
        
        # First, send the fail message - cards are still visible!
        await self.broadcast(room_id, {
            "type": "turn_failed",
            "player": player.name,
            "message": f"Different numbers! {player.name}'s turn ends.",
            "delay_return": True  # Tell client to show cards before hiding
        })
        
        # Wait 2.5 seconds so players can see the revealed cards
        await asyncio.sleep(2.5)
        
        # Now return all revealed cards
        await self.return_revealed_cards(room_id)
        
        # Next turn
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
        
        await self.broadcast(room_id, {
            "type": "game_over",
            "winner": player.name,
            "winner_id": player.id,
            "reason": reason,
            "message": f"🏆 {player.name} wins! {reason}",
            "final_scores": [
                {"name": p.name, "trios": len(p.trios)} 
                for p in sorted(room.players.values(), key=lambda x: len(x.trios), reverse=True)
            ]
        })
    
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
                await self.reveal_from_middle(room_id, player_id, card_id)
        
        elif action == "reveal_player":
            target_id = data.get("target_player_id")
            position = data.get("position")  # "lowest" or "highest"
            if target_id and position:
                await self.reveal_from_player(room_id, player_id, target_id, position)
        
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


# Global game manager instance
game_manager = TrioGameManager()
