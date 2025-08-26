"""
Oliver Velez Advanced Position Management System.

Implements the exact OV position management methodology:
- 3-stage scaling out (T1: 30%, T2: 40%, T3: 30%)
- Progressive trailing stops (breakeven → bar-by-bar → 8MA → 20MA)
- MA-based trailing for runners
- TIF (Time in Formation) handling
"""
import asyncio
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Tuple
from decimal import Decimal
from enum import Enum
from dataclasses import dataclass

from app.services.order_manager import order_manager
from app.services.market_data import market_data_service
from app.strategies.indicators import TechnicalIndicators
from app.core.database import get_db_session
from app.models.position import Position, PositionStatus

logger = logging.getLogger(__name__)


class TrailingStopLevel(Enum):
    """Progressive trailing stop levels."""
    INITIAL = "initial_stop"
    BREAKEVEN = "breakeven"
    BAR_BY_BAR = "bar_by_bar"
    MA_8 = "ma_8_trail"
    MA_20 = "ma_20_trail"


class ScaleOutLevel(Enum):
    """Scale out target levels."""
    T1 = "target_1"
    T2 = "target_2" 
    T3 = "target_3"


@dataclass
class ScaleOutPlan:
    """Defines the scale-out plan for a position."""
    t1_percent: float = 0.30  # 30% at T1
    t2_percent: float = 0.40  # 40% at T2
    t3_percent: float = 0.30  # 30% at T3 (runner)
    
    t1_price: float = 0.0
    t2_price: float = 0.0
    t3_price: float = 0.0
    
    t1_executed: bool = False
    t2_executed: bool = False
    t3_executed: bool = False


@dataclass
class PositionState:
    """Tracks the current state of a managed position."""
    symbol: str
    original_quantity: int
    remaining_quantity: int
    entry_price: float
    initial_stop: float
    
    # Current management state
    trailing_level: TrailingStopLevel
    current_stop: float
    scale_out_plan: ScaleOutPlan
    
    # Tracking
    bars_in_favor: int = 0
    max_favorable_price: float = 0.0
    last_update: datetime = None
    
    # MA levels for trailing
    ma_8_level: float = 0.0
    ma_20_level: float = 0.0


class OVPositionManager:
    """Oliver Velez advanced position management system."""
    
    def __init__(self):
        self.active_positions: Dict[str, PositionState] = {}
        self.indicators = TechnicalIndicators()
        
        # Configuration
        self.bars_to_breakeven = 2  # Move to breakeven after 2 favorable bars
        self.bars_to_bar_trail = 2  # Switch to bar-by-bar after 2 more bars
        self.ma_trail_switch_bars = 5  # Switch to MA trail after this many bars
        
    async def create_managed_position(self, symbol: str, entry_price: float, 
                                    stop_loss: float, quantity: int,
                                    risk_reward_ratios: Tuple[float, float, float] = (1.5, 2.5, 4.0)) -> str:
        """Create a new managed position with OV scaling plan."""
        try:
            # Calculate target levels based on risk-reward ratios
            risk_amount = abs(entry_price - stop_loss)
            
            t1_price = entry_price + (risk_amount * risk_reward_ratios[0])
            t2_price = entry_price + (risk_amount * risk_reward_ratios[1])  
            t3_price = entry_price + (risk_amount * risk_reward_ratios[2])
            
            # Create scale-out plan
            scale_plan = ScaleOutPlan(
                t1_price=t1_price,
                t2_price=t2_price,
                t3_price=t3_price
            )
            
            # Create position state
            position_state = PositionState(
                symbol=symbol,
                original_quantity=quantity,
                remaining_quantity=quantity,
                entry_price=entry_price,
                initial_stop=stop_loss,
                trailing_level=TrailingStopLevel.INITIAL,
                current_stop=stop_loss,
                scale_out_plan=scale_plan,
                max_favorable_price=entry_price,
                last_update=datetime.now()
            )
            
            # Add to managed positions
            self.active_positions[symbol] = position_state
            
            logger.info(f"Created managed position for {symbol}: {quantity} shares at ${entry_price}")
            logger.info(f"Targets: T1=${t1_price:.2f}, T2=${t2_price:.2f}, T3=${t3_price:.2f}")
            
            return f"managed_{symbol}_{datetime.now().strftime('%H%M%S')}"
            
        except Exception as e:
            logger.error(f"Error creating managed position for {symbol}: {e}")
            return ""
    
    async def update_position_management(self, symbol: str) -> Dict[str, Any]:
        """Update position management for a symbol."""
        try:
            if symbol not in self.active_positions:
                return {"error": f"No managed position found for {symbol}"}
            
            position = self.active_positions[symbol]
            
            # Get current market data
            df = market_data_service.get_historical_data(symbol, period='1d', interval='1m')
            if df is None or df.empty:
                return {"error": "No market data available"}
            
            current_price = df['close'].iloc[-1]
            actions_taken = []
            
            # Update max favorable price
            if current_price > position.max_favorable_price:
                position.max_favorable_price = current_price
            
            # Check for scale-out opportunities
            scale_actions = await self._check_scale_out_levels(position, current_price)
            actions_taken.extend(scale_actions)
            
            # Update trailing stop logic
            trail_actions = await self._update_trailing_stop(position, current_price, df)
            actions_taken.extend(trail_actions)
            
            # Check if stop hit
            if current_price <= position.current_stop:
                stop_action = await self._execute_stop_loss(position, current_price)
                if stop_action:
                    actions_taken.append(stop_action)
            
            # Log all actions taken to analysis logger
            if actions_taken:
                try:
                    from app.services.analysis_logger import analysis_logger
                    for action in actions_taken:
                        analysis_logger.log_position_update(symbol, action.get('action', 'unknown'), action)
                except Exception as e:
                    logger.error(f"Error logging position actions: {e}")
            
            position.last_update = datetime.now()
            
            return {
                "symbol": symbol,
                "actions_taken": actions_taken,
                "current_price": current_price,
                "current_stop": position.current_stop,
                "trailing_level": position.trailing_level.value,
                "remaining_quantity": position.remaining_quantity,
                "bars_in_favor": position.bars_in_favor,
                "scale_out_status": {
                    "t1_executed": position.scale_out_plan.t1_executed,
                    "t2_executed": position.scale_out_plan.t2_executed,
                    "t3_executed": position.scale_out_plan.t3_executed
                }
            }
            
        except Exception as e:
            logger.error(f"Error updating position management for {symbol}: {e}")
            return {"error": str(e)}
    
    async def _check_scale_out_levels(self, position: PositionState, current_price: float) -> List[Dict[str, Any]]:
        """Check and execute scale-out levels."""
        actions = []
        plan = position.scale_out_plan
        
        try:
            # Check T1 scale-out (30%)
            if not plan.t1_executed and current_price >= plan.t1_price:
                shares_to_sell = int(position.original_quantity * plan.t1_percent)
                
                order_id = order_manager.place_market_order(
                    symbol=position.symbol,
                    side='sell',
                    quantity=shares_to_sell
                )
                
                if order_id:
                    plan.t1_executed = True
                    position.remaining_quantity -= shares_to_sell
                    
                    actions.append({
                        "action": "scale_out_t1",
                        "shares_sold": shares_to_sell,
                        "sale_price": current_price,
                        "order_id": order_id,
                        "percentage": "30%"
                    })
                    
                    logger.info(f"T1 scale-out executed for {position.symbol}: {shares_to_sell} shares at ${current_price}")
            
            # Check T2 scale-out (40%)
            if plan.t1_executed and not plan.t2_executed and current_price >= plan.t2_price:
                shares_to_sell = int(position.original_quantity * plan.t2_percent)
                
                order_id = order_manager.place_market_order(
                    symbol=position.symbol,
                    side='sell',
                    quantity=shares_to_sell
                )
                
                if order_id:
                    plan.t2_executed = True
                    position.remaining_quantity -= shares_to_sell
                    
                    actions.append({
                        "action": "scale_out_t2",
                        "shares_sold": shares_to_sell,
                        "sale_price": current_price,
                        "order_id": order_id,
                        "percentage": "40%"
                    })
                    
                    logger.info(f"T2 scale-out executed for {position.symbol}: {shares_to_sell} shares at ${current_price}")
            
            # T3 is handled by MA trailing, not automatic scale-out
            
        except Exception as e:
            logger.error(f"Error in scale-out execution for {position.symbol}: {e}")
        
        return actions
    
    async def _update_trailing_stop(self, position: PositionState, current_price: float, df) -> List[Dict[str, Any]]:
        """Update trailing stop using progressive OV methodology."""
        actions = []
        
        try:
            # Count bars in favor
            if current_price > position.entry_price:
                position.bars_in_favor += 1
            else:
                position.bars_in_favor = 0
            
            old_stop = position.current_stop
            old_level = position.trailing_level
            
            # Progressive trailing stop logic
            if position.trailing_level == TrailingStopLevel.INITIAL:
                # Move to breakeven after 2 favorable bars
                if position.bars_in_favor >= self.bars_to_breakeven:
                    position.current_stop = position.entry_price
                    position.trailing_level = TrailingStopLevel.BREAKEVEN
            
            elif position.trailing_level == TrailingStopLevel.BREAKEVEN:
                # Switch to bar-by-bar trailing after more favorable movement
                if position.bars_in_favor >= (self.bars_to_breakeven + self.bars_to_bar_trail):
                    position.trailing_level = TrailingStopLevel.BAR_BY_BAR
            
            elif position.trailing_level == TrailingStopLevel.BAR_BY_BAR:
                # Bar-by-bar trailing: stop below prior bar low
                if len(df) >= 2:
                    prior_bar_low = df['low'].iloc[-2]
                    new_stop = prior_bar_low - 0.01  # 1 cent buffer
                    
                    # Only move stop up, never down
                    if new_stop > position.current_stop:
                        position.current_stop = new_stop
                
                # Switch to 8-MA trail after enough bars
                if position.bars_in_favor >= self.ma_trail_switch_bars:
                    position.trailing_level = TrailingStopLevel.MA_8
            
            elif position.trailing_level == TrailingStopLevel.MA_8:
                # 8-period EMA trailing
                if len(df) >= 8:
                    ema_8 = self.indicators.calculate_ema(df['close'], 8).iloc[-1]
                    position.ma_8_level = ema_8
                    
                    # Trail with 8-EMA
                    if ema_8 > position.current_stop:
                        position.current_stop = ema_8 - 0.02  # Small buffer
                
                # Switch to 20-MA for final runner trail
                if position.scale_out_plan.t2_executed:
                    position.trailing_level = TrailingStopLevel.MA_20
            
            elif position.trailing_level == TrailingStopLevel.MA_20:
                # 20-period EMA trailing for final runner
                if len(df) >= 20:
                    ema_20 = self.indicators.calculate_ema(df['close'], 20).iloc[-1]
                    position.ma_20_level = ema_20
                    
                    # Trail with 20-EMA
                    if ema_20 > position.current_stop:
                        position.current_stop = ema_20 - 0.03  # Slightly wider buffer
            
            # Log stop updates
            if abs(position.current_stop - old_stop) > 0.001 or position.trailing_level != old_level:
                actions.append({
                    "action": "trailing_stop_update",
                    "old_stop": old_stop,
                    "new_stop": position.current_stop,
                    "old_level": old_level.value,
                    "new_level": position.trailing_level.value,
                    "bars_in_favor": position.bars_in_favor
                })
                
                logger.info(f"Trailing stop updated for {position.symbol}: "
                          f"${old_stop:.2f} → ${position.current_stop:.2f} "
                          f"({old_level.value} → {position.trailing_level.value})")
            
        except Exception as e:
            logger.error(f"Error updating trailing stop for {position.symbol}: {e}")
        
        return actions
    
    async def _execute_stop_loss(self, position: PositionState, current_price: float) -> Optional[Dict[str, Any]]:
        """Execute stop-loss exit."""
        try:
            if position.remaining_quantity <= 0:
                return None
            
            order_id = order_manager.place_market_order(
                symbol=position.symbol,
                side='sell',
                quantity=position.remaining_quantity
            )
            
            if order_id:
                # Remove from active positions
                del self.active_positions[position.symbol]
                
                logger.info(f"Stop-loss executed for {position.symbol}: "
                          f"{position.remaining_quantity} shares at ${current_price:.2f}")
                
                return {
                    "action": "stop_loss_exit",
                    "shares_sold": position.remaining_quantity,
                    "exit_price": current_price,
                    "stop_price": position.current_stop,
                    "trailing_level": position.trailing_level.value,
                    "order_id": order_id
                }
            
            return None
            
        except Exception as e:
            logger.error(f"Error executing stop loss for {position.symbol}: {e}")
            return None
    
    async def force_close_position(self, symbol: str, reason: str = "manual_close") -> Optional[Dict[str, Any]]:
        """Force close a managed position."""
        try:
            if symbol not in self.active_positions:
                return {"error": f"No managed position found for {symbol}"}
            
            position = self.active_positions[symbol]
            
            if position.remaining_quantity <= 0:
                del self.active_positions[symbol]
                return {"message": "Position already fully closed"}
            
            # Get current price
            current_price = market_data_service.get_current_price(symbol)
            if not current_price:
                return {"error": "Unable to get current price"}
            
            order_id = order_manager.place_market_order(
                symbol=symbol,
                side='sell',
                quantity=position.remaining_quantity
            )
            
            if order_id:
                shares_sold = position.remaining_quantity
                del self.active_positions[symbol]
                
                logger.info(f"Force closed position for {symbol}: "
                          f"{shares_sold} shares at ${current_price:.2f} - Reason: {reason}")
                
                return {
                    "action": "force_close",
                    "shares_sold": shares_sold,
                    "exit_price": current_price,
                    "reason": reason,
                    "order_id": order_id
                }
            else:
                return {"error": "Failed to place closing order"}
                
        except Exception as e:
            logger.error(f"Error force closing position for {symbol}: {e}")
            return {"error": str(e)}
    
    def get_position_status(self, symbol: str) -> Dict[str, Any]:
        """Get detailed status of a managed position."""
        if symbol not in self.active_positions:
            return {"error": f"No managed position found for {symbol}"}
        
        position = self.active_positions[symbol]
        plan = position.scale_out_plan
        
        return {
            "symbol": symbol,
            "original_quantity": position.original_quantity,
            "remaining_quantity": position.remaining_quantity,
            "entry_price": position.entry_price,
            "current_stop": position.current_stop,
            "trailing_level": position.trailing_level.value,
            "bars_in_favor": position.bars_in_favor,
            "max_favorable_price": position.max_favorable_price,
            "scale_out_plan": {
                "t1_price": plan.t1_price,
                "t2_price": plan.t2_price,
                "t3_price": plan.t3_price,
                "t1_executed": plan.t1_executed,
                "t2_executed": plan.t2_executed,
                "t3_executed": plan.t3_executed
            },
            "last_update": position.last_update.isoformat() if position.last_update else None
        }
    
    def get_all_managed_positions(self) -> Dict[str, Dict[str, Any]]:
        """Get status of all managed positions."""
        return {symbol: self.get_position_status(symbol) 
                for symbol in self.active_positions.keys()}
    
    async def end_of_day_cleanup(self) -> List[Dict[str, Any]]:
        """Close all managed positions at end of trading day."""
        actions = []
        
        for symbol in list(self.active_positions.keys()):
            action = await self.force_close_position(symbol, "end_of_day")
            if action and "error" not in action:
                actions.append(action)
        
        return actions


# Create global position manager instance
ov_position_manager = OVPositionManager()