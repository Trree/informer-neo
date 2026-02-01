from sqlalchemy import Boolean, Column, Integer, String, DateTime, ForeignKey, Table, BigInteger
from sqlalchemy.orm import relationship, declarative_base
from datetime import datetime

Base = declarative_base()

class Account(Base):
    """
    The telegram account being used as the sock puppet
    """
    __tablename__ = 'account'
    id = Column(Integer, index=True, primary_key=True, autoincrement=True)
    account_id = Column(BigInteger, nullable=False, unique=True, index=True)
    account_api_id = Column(Integer, nullable=False)
    account_api_hash = Column(String(50), nullable=False)
    account_is_bot = Column(Boolean, default=False)
    account_is_verified = Column(Boolean, default=False)
    account_is_restricted = Column(Boolean, default=False)
    account_first_name = Column(String(50))
    account_last_name = Column(String(50))
    account_user_name = Column(String(100), nullable=False)
    account_phone = Column(String(25), unique=True, nullable=False)
    account_tlogin = Column(DateTime)
    account_is_enabled = Column(Boolean, default=True)
    account_tcreate = Column(DateTime, default=datetime.utcnow)
    account_tmodified = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    channels = relationship('Channel', back_populates='accounts')
    messages = relationship('Message', back_populates='account')

    def __repr__(self):
        return f"<Account(id={self.id}, account_id={self.account_id}, username={self.account_user_name})>"


class Channel(Base):
    """
    The telegram channel the user is in
    """
    __tablename__ = 'channel'
    id = Column(Integer, primary_key=True, index=True)
    channel_id = Column(Integer, unique=True, index=True, nullable=True)  # The URL can come first but the channel ID populated later
    channel_name = Column(String(256))
    channel_title = Column(String(256))
    channel_url = Column(String(256))
    account_id = Column(BigInteger, ForeignKey('account.account_id'), nullable=False)  # The account ID (bot) that spawned the channel
    channel_is_mega_group = Column(Boolean)
    channel_is_group = Column(Boolean)
    channel_is_private = Column(Boolean)
    channel_is_broadcast = Column(Boolean)
    channel_access_hash = Column(String(50))
    channel_size = Column(Integer)
    channel_is_enabled = Column(Boolean, default=True)
    channel_tcreate = Column(DateTime, default=datetime.utcnow)

    messages = relationship('Message')

    accounts = relationship('Account', back_populates='channels')
    notifications = relationship('Notification', back_populates='channel')

    def __repr__(self):
        return f"<Channel(id={self.id}, channel_id={self.channel_id}, name={self.channel_name})>"


class ChatUser(Base):
    """
    The participant of a chat on telegram
    """
    __tablename__ = 'chat_user'
    id = Column(Integer, primary_key=True, index=True)
    chat_user_id = Column(BigInteger, unique=True, index=True, nullable=False)
    chat_user_is_bot = Column(Boolean, default=False)
    chat_user_is_verified = Column(Boolean, default=False)
    chat_user_is_restricted = Column(Boolean, default=False)
    chat_user_first_name = Column(String(50))
    chat_user_last_name = Column(String(50))
    chat_user_name = Column(String(100))
    chat_user_phone = Column(String(25))
    chat_user_tlogin = Column(DateTime)
    chat_user_tcreate = Column(DateTime, default=datetime.utcnow)
    chat_user_tmodified = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    messages = relationship('Message')

    def __repr__(self):
        return f"<ChatUser(id={self.id}, chat_user_id={self.chat_user_id}, name={self.chat_user_name})>"


class Keyword(Base):
    """
    This is the keyword to be alerted by
    """
    __tablename__ = 'keyword'
    keyword_id = Column(Integer, primary_key=True, index=True)
    keyword_description = Column(String(256), nullable=False)
    keyword_regex = Column(String(256), unique=True, nullable=False)
    keyword_is_enabled = Column(Boolean, default=True)
    keyword_tmodified = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    keyword_tcreate = Column(DateTime, default=datetime.utcnow)

    notifications = relationship('Notification', back_populates='keyword')

    def __repr__(self):
        return f"<Keyword(id={self.keyword_id}, description={self.keyword_description}, regex={self.keyword_regex})>"


class Message(Base):
    """
    The actual message from a channel and from a user
    """
    __tablename__ = 'message'
    message_id = Column(Integer, primary_key=True, index=True)
    chat_user_id = Column(BigInteger, ForeignKey('chat_user.chat_user_id'), nullable=False)
    account_id = Column(BigInteger, ForeignKey('account.account_id'), nullable=False)  # The account ID (bot)
    channel_id = Column(Integer, ForeignKey('channel.channel_id'), nullable=False)
    keyword_id = Column(Integer, ForeignKey('keyword.keyword_id'), nullable=False)
    message_text = Column(String(10000))
    message_is_mention = Column(Boolean, default=False)
    message_is_scheduled = Column(Boolean, default=False)
    message_is_fwd = Column(Boolean, default=False)
    message_is_reply = Column(Boolean, default=False)
    message_is_bot = Column(Boolean, default=False)
    message_is_group = Column(Boolean, default=False)
    message_is_private = Column(Boolean, default=False)
    message_is_channel = Column(Boolean, default=False)
    message_channel_size = Column(Integer)
    message_tcreate = Column(DateTime, default=datetime.utcnow)

    user = relationship('ChatUser', back_populates='messages')
    account = relationship('Account', back_populates='messages')
    channel = relationship('Channel', back_populates='messages')
    notifications = relationship('Notification', back_populates='message')

    def __repr__(self):
        return f"<Message(id={self.message_id}, channel_id={self.channel_id}, text={self.message_text[:50]}...)>"


class Monitor(Base):
    """
    Channels to join and monitor
    """
    __tablename__ = 'monitor'
    monitor_id = Column(Integer, primary_key=True, index=True)
    channel_id = Column(Integer, ForeignKey('channel.id'), nullable=False)
    account_id = Column(BigInteger, ForeignKey('account.account_id'), nullable=False)  # The account ID (bot)
    monitor_tcreate = Column(DateTime, default=datetime.utcnow)
    monitor_tmodified = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    channel = relationship('Channel')

    def __repr__(self):
        return f"<Monitor(id={self.monitor_id}, channel_id={self.channel_id}, account_id={self.account_id})>"


class Notification(Base):
    """
    A log of notifications of keywords detected
    """
    __tablename__ = 'notification'
    id = Column(Integer, primary_key=True, index=True)
    keyword_id = Column(Integer, ForeignKey('keyword.keyword_id'), nullable=False)
    message_id = Column(Integer, ForeignKey('message.message_id'), nullable=False)
    channel_id = Column(Integer, ForeignKey('channel.channel_id'), nullable=False)
    account_id = Column(BigInteger, ForeignKey('account.account_id'), nullable=False)  # The account ID (bot)
    chat_user_id = Column(BigInteger, ForeignKey('chat_user.chat_user_id'), nullable=False)
    notification_tnotify = Column(DateTime, default=datetime.utcnow)

    keyword = relationship('Keyword', back_populates='notifications')
    message = relationship('Message', back_populates='notifications')
    channel = relationship('Channel', back_populates='notifications')
    user = relationship('ChatUser')

    def __repr__(self):
        return f"<Notification(id={self.id}, keyword_id={self.keyword_id}, message_id={self.message_id})>"
