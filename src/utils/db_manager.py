import os
import json
import logging
from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, Enum, ForeignKey
from sqlalchemy.orm import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
from datetime import datetime
import enum

Base = declarative_base()

class TradeStatusEnum(enum.Enum):
    PENDING = "pending"     # Signal generated, not yet triggered
    TRIGGERED = "triggered" # Trade active
    STOP_LOSS = "stop_loss" # Trade closed by stop-loss
    TAKE_PROFIT = "take_profit" # Trade closed by take-profit
    CLOSED = "closed"       # Trade closed manually or otherwise

class TradeSignal(Base):
    __tablename__ = 'trade_signals'

    id = Column(Integer, primary_key=True)
    timestamp = Column(DateTime, default=datetime.utcnow)
    ticker = Column(String(10), index=True)
    timeframe = Column(String(5))
    entry_price = Column(Float)
    stop_loss = Column(Float)
    take_profit = Column(Float)
    risk_reward = Column(Float)
    strategy_version = Column(String(20))
    indicator_data = Column(String) # JSON string of indicator values
    trigger_conditions = Column(String) # JSON string of conditions met
    status = Column(Enum(TradeStatusEnum), default=TradeStatusEnum.PENDING)

    updates = relationship("TradeUpdate", back_populates="signal")

class TradeUpdate(Base):
    __tablename__ = 'trade_updates'

    id = Column(Integer, primary_key=True)
    signal_id = Column(Integer, ForeignKey('trade_signals.id'))
    timestamp = Column(DateTime, default=datetime.utcnow)
    old_status = Column(Enum(TradeStatusEnum))
    new_status = Column(Enum(TradeStatusEnum))
    message = Column(String)

    signal = relationship("TradeSignal", back_populates="updates")

class DBManager:
    def __init__(self, config_path='config/config.json'):
        project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '../..'))
        self.config_path = os.path.join(project_root, config_path)
        self.config = self._load_config()

        intraday_config = self.config.get('intraday', {})
        self.db_url = intraday_config.get('database_url')

        if not self.db_url or "postgresql://user:password" in self.db_url:
            logging.warning("PostgreSQL URL not configured. Using SQLite as fallback for local development.")
            self.db_url = "sqlite:///trading.db"

        try:
            self.engine = create_engine(self.db_url)
            # Use Base.metadata.create_all(self.engine) inside __init__
            Base.metadata.create_all(self.engine)
            self.Session = sessionmaker(bind=self.engine)
            logging.info(f"Database manager initialized with: {self.db_url.split('@')[-1] if '@' in self.db_url else self.db_url}")
        except Exception as e:
            logging.error(f"Failed to initialize database: {e}")
            self.Session = None

    def _load_config(self):
        try:
            with open(self.config_path, 'r') as f:
                return json.load(f)
        except Exception as e:
            logging.error(f"Error loading config in DBManager: {e}")
            return {}

    def get_session(self):
        if self.Session:
            return self.Session()
        return None

    def add_signal(self, ticker, timeframe, entry, sl, tp, rr, indicators, conditions, version):
        session = self.get_session()
        if not session: return None

        try:
            signal = TradeSignal(
                ticker=ticker,
                timeframe=timeframe,
                entry_price=entry,
                stop_loss=sl,
                take_profit=tp,
                risk_reward=rr,
                indicator_data=json.dumps(indicators),
                trigger_conditions=json.dumps(conditions),
                strategy_version=version,
                status=TradeStatusEnum.PENDING
            )
            session.add(signal)
            session.commit()
            logging.info(f"Signal added for {ticker} at {entry}")
            return signal.id
        except Exception as e:
            session.rollback()
            logging.error(f"Error adding signal: {e}")
            return None
        finally:
            session.close()

    def update_status(self, signal_id, new_status, message=""):
        session = self.get_session()
        if not session: return False

        try:
            signal = session.query(TradeSignal).filter(TradeSignal.id == signal_id).first()
            if signal:
                old_status = signal.status
                signal.status = new_status

                update = TradeUpdate(
                    signal_id=signal_id,
                    old_status=old_status,
                    new_status=new_status,
                    message=message
                )
                session.add(update)
                session.commit()
                logging.info(f"Signal {signal_id} ({signal.ticker}) status updated: {old_status} -> {new_status}")
                return True
            return False
        except Exception as e:
            session.rollback()
            logging.error(f"Error updating status for signal {signal_id}: {e}")
            return False
        finally:
            session.close()

    def get_active_signals(self):
        session = self.get_session()
        if not session: return []

        try:
            signals = session.query(TradeSignal).filter(
                TradeSignal.status.in_([TradeStatusEnum.PENDING, TradeStatusEnum.TRIGGERED])
            ).all()
            return signals
        except Exception as e:
            logging.error(f"Error fetching active signals: {e}")
            return []
        finally:
            session.close()
