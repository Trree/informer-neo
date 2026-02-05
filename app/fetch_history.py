"""
历史消息拉取工具
用于从指定频道拉取历史消息并进行关键词匹配
"""
import sys
import os
import asyncio
import argparse
import logging
from datetime import datetime, timedelta
from pathlib import Path
from dotenv import load_dotenv
from telethon import TelegramClient
from telethon.tl.types import PeerChannel
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from models import Account, Channel, Keyword, Message, ChatUser, Notification

# 设置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# 加载环境变量
env_file = 'informer.env' if os.path.isfile('informer.env') else '../informer.env'
dotenv_path = Path(env_file)
load_dotenv(dotenv_path=dotenv_path)

# 数据库连接
DATABASE_URL = f"postgresql://{os.getenv('POSTGRES_USER')}:{os.getenv('POSTGRES_PASSWORD')}@{os.getenv('POSTGRES_HOST')}:{os.getenv('POSTGRES_PORT')}/{os.getenv('POSTGRES_DB')}"
engine = create_engine(DATABASE_URL)
Session = sessionmaker(bind=engine)


class HistoryFetcher:
    def __init__(self):
        self.db_session = Session()
        self.client = None
        self.account = None

    async def initialize(self):
        """初始化 Telegram 客户端"""
        # 获取第一个启用的账户
        self.account = self.db_session.query(Account).filter_by(account_is_enabled=True).first()

        if not self.account:
            raise Exception("没有找到启用的账户")

        # 创建 session 目录
        session_dir = os.path.join(os.path.dirname(__file__), 'session')
        os.makedirs(session_dir, exist_ok=True)

        session_file = os.path.join(session_dir, self.account.account_phone.replace('+', ''))
        self.client = TelegramClient(session_file, self.account.account_api_id, self.account.account_api_hash)

        await self.client.connect()

        if not await self.client.is_user_authorized():
            raise Exception("账户未授权，请先运行主程序进行授权")

        logger.info(f"已连接账户: {self.account.account_user_name}")

    async def fetch_messages(self, channel_id, limit=None, days=None, offset_date=None):
        """
        从指定频道拉取历史消息

        Args:
            channel_id: 频道ID
            limit: 拉取消息数量限制
            days: 拉取最近N天的消息
            offset_date: 从指定日期开始拉取
        """
        # 查询频道信息
        channel = self.db_session.query(Channel).filter_by(channel_id=channel_id).first()

        if not channel:
            raise Exception(f"频道 {channel_id} 不存在，请先在管理面板中添加")

        if not channel.channel_is_enabled:
            logger.warning(f"频道 {channel.channel_name} 未启用")

        logger.info(f"开始拉取频道: {channel.channel_name} (ID: {channel_id})")

        # 获取所有启用的关键词
        keywords = self.db_session.query(Keyword).filter_by(keyword_is_enabled=True).all()
        logger.info(f"已加载 {len(keywords)} 个关键词")

        # 计算时间范围
        min_date = None
        if days:
            min_date = datetime.now() - timedelta(days=days)
            logger.info(f"拉取最近 {days} 天的消息 (从 {min_date.strftime('%Y-%m-%d %H:%M:%S')})")
        elif offset_date:
            min_date = offset_date
            logger.info(f"从 {min_date.strftime('%Y-%m-%d %H:%M:%S')} 开始拉取")

        # 拉取消息
        total_count = 0
        matched_count = 0
        saved_count = 0

        try:
            # 构建 PeerChannel
            peer = PeerChannel(channel_id)

            async for message in self.client.iter_messages(
                peer,
                limit=limit,
                offset_date=min_date,
                reverse=False  # 从新到旧
            ):
                total_count += 1

                if total_count % 100 == 0:
                    logger.info(f"已处理 {total_count} 条消息，匹配 {matched_count} 条")

                # 检查消息是否有文本
                if not message.text:
                    continue

                # 检查消息是否已存在（通过消息文本和时间判断，因为 message_id 是自增的）
                existing_message = self.db_session.query(Message).filter_by(
                    message_text=message.text,
                    channel_id=channel.channel_id,
                    message_tcreate=message.date
                ).first()

                if existing_message:
                    continue

                # 匹配关键词
                matched_keywords = []
                for keyword in keywords:
                    import re
                    if re.search(keyword.keyword_regex, message.text, re.IGNORECASE):
                        matched_keywords.append(keyword)
                        matched_count += 1

                # 如果没有匹配的关键词，跳过
                if not matched_keywords:
                    continue

                # 保存发送者信息
                sender = await message.get_sender()
                chat_user_id = None

                if sender:
                    chat_user = self.db_session.query(ChatUser).filter_by(
                        chat_user_id=sender.id
                    ).first()

                    if not chat_user:
                        chat_user = ChatUser(
                            chat_user_id=sender.id,
                            chat_user_name=getattr(sender, 'username', None),
                            chat_user_first_name=getattr(sender, 'first_name', None),
                            chat_user_last_name=getattr(sender, 'last_name', None),
                            chat_user_phone=getattr(sender, 'phone', None),
                            chat_user_is_bot=getattr(sender, 'bot', False),
                            chat_user_is_verified=getattr(sender, 'verified', False),
                            chat_user_tcreate=datetime.now()
                        )
                        self.db_session.add(chat_user)
                        self.db_session.commit()  # 立即提交以获取ID

                    chat_user_id = sender.id  # 使用 Telegram 的 user ID，不是数据库自增ID

                # 保存消息
                for keyword in matched_keywords:
                    new_message = Message(
                        # message_id 是自增的，不需要手动设置
                        channel_id=channel.channel_id,
                        keyword_id=keyword.keyword_id,
                        chat_user_id=chat_user_id,
                        account_id=self.account.account_id,
                        message_text=message.text,
                        message_tcreate=message.date
                    )
                    self.db_session.add(new_message)
                    self.db_session.flush()  # 确保获取自增的 message_id

                    # 创建通知记录（历史数据不实际发送通知）
                    notification = Notification(
                        keyword_id=keyword.keyword_id,
                        message_id=new_message.message_id,  # 使用数据库自增的 ID
                        channel_id=channel.channel_id,
                        account_id=self.account.account_id,
                        chat_user_id=chat_user_id,
                        notification_tnotify=datetime.now()
                    )
                    self.db_session.add(notification)
                    saved_count += 1

                # 每50条提交一次（因为每个匹配可能有多个关键词）
                if saved_count % 50 == 0:
                    self.db_session.commit()

            # 最后提交
            self.db_session.commit()

            logger.info(f"拉取完成！")
            logger.info(f"总消息数: {total_count}")
            logger.info(f"匹配消息数: {matched_count}")
            logger.info(f"保存记录数: {saved_count}")

        except Exception as e:
            self.db_session.rollback()
            logger.error(f"拉取消息时出错: {str(e)}")
            raise

    async def list_channels(self):
        """列出所有可用的频道"""
        channels = self.db_session.query(Channel).all()

        if not channels:
            logger.info("没有找到任何频道，请先在管理面板中添加频道")
            return

        logger.info(f"\n可用频道列表 (共 {len(channels)} 个):")
        logger.info("-" * 80)

        for channel in channels:
            status = "✓ 启用" if channel.channel_is_enabled else "✗ 禁用"
            logger.info(f"ID: {channel.channel_id:15} | {status} | {channel.channel_name}")

        logger.info("-" * 80)

    async def close(self):
        """关闭连接"""
        if self.client:
            await self.client.disconnect()
        if self.db_session:
            self.db_session.close()


async def main():
    parser = argparse.ArgumentParser(
        description='从 Telegram 频道拉取历史消息',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  # 列出所有频道
  python fetch_history.py --list

  # 拉取指定频道最近1000条消息
  python fetch_history.py --channel 1234567890 --limit 1000

  # 拉取指定频道最近7天的消息
  python fetch_history.py --channel 1234567890 --days 7

  # 拉取指定频道最近30天的消息，限制最多5000条
  python fetch_history.py --channel 1234567890 --days 30 --limit 5000
        """
    )

    parser.add_argument('--list', action='store_true', help='列出所有可用的频道')
    parser.add_argument('--channel', type=int, help='频道ID')
    parser.add_argument('--limit', type=int, help='拉取消息数量限制')
    parser.add_argument('--days', type=int, help='拉取最近N天的消息')

    args = parser.parse_args()

    fetcher = HistoryFetcher()

    try:
        await fetcher.initialize()

        if args.list:
            await fetcher.list_channels()
        elif args.channel:
            await fetcher.fetch_messages(
                channel_id=args.channel,
                limit=args.limit,
                days=args.days
            )
        else:
            parser.print_help()

    except Exception as e:
        logger.error(f"错误: {str(e)}")
        sys.exit(1)

    finally:
        await fetcher.close()


if __name__ == '__main__':
    asyncio.run(main())
