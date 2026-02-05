"""
Flask-Admin管理面板 - 自动生成的CRUD界面
提供频道、关键词、通知等的可视化管理
"""
from flask import Flask, redirect, url_for, flash, render_template, request
from flask_admin import Admin, AdminIndexView, expose
from flask_admin.contrib.sqla import ModelView
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from sqlalchemy import create_engine, func
from sqlalchemy.orm import sessionmaker
from models import Base, Account, Channel, ChatUser, Keyword, Message, Monitor, Notification
import os
import asyncio
from datetime import datetime
from telethon import TelegramClient
from dotenv import load_dotenv
from werkzeug.security import check_password_hash, generate_password_hash

# 加载环境变量
# 使用相对于脚本文件的路径，而不是相对于当前工作目录
env_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'informer.env')
load_dotenv(env_path)

# 数据库连接
DATABASE_URL = f"postgresql://{os.getenv('POSTGRES_USER')}:{os.getenv('POSTGRES_PASSWORD')}@{os.getenv('POSTGRES_HOST')}:{os.getenv('POSTGRES_PORT')}/{os.getenv('POSTGRES_DB')}"
engine = create_engine(DATABASE_URL)
Session = sessionmaker(bind=engine)
db_session = Session()

# 创建Flask应用
app = Flask(__name__)
app.config['SECRET_KEY'] = 'informer-admin-secret-key-change-in-production'
app.config['FLASK_ADMIN_SWATCH'] = 'cerulean'  # Bootstrap主题

# 初始化Flask-Login
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'
login_manager.login_message = '请先登录以访问管理面板'

# 简单的用户类
class User(UserMixin):
    def __init__(self, id):
        self.id = id

# 从环境变量或默认值获取管理员凭据
ADMIN_USERNAME = os.getenv('ADMIN_USERNAME', 'admin')
ADMIN_PASSWORD_HASH = os.getenv('ADMIN_PASSWORD_HASH', generate_password_hash('admin20260205'))

@login_manager.user_loader
def load_user(user_id):
    if user_id == ADMIN_USERNAME:
        return User(user_id)
    return None


# 自定义首页视图 - 需要登录
class MyAdminIndexView(AdminIndexView):
    @expose('/')
    def index(self):
        if not current_user.is_authenticated:
            return redirect(url_for('login'))

        # 获取统计数据
        stats = {
            'accounts': db_session.query(func.count(Account.id)).scalar(),
            'channels': db_session.query(func.count(Channel.id)).scalar(),
            'keywords': db_session.query(func.count(Keyword.keyword_id)).scalar(),
            'notifications': db_session.query(func.count(Notification.id)).scalar(),
            'messages': db_session.query(func.count(Message.message_id)).scalar(),
        }

        # 获取最近的通知
        recent_notifications = db_session.query(Notification).order_by(
            Notification.notification_tnotify.desc()
        ).limit(10).all()

        return self.render('admin/custom_index.html', stats=stats, recent_notifications=recent_notifications)


# 自定义模型视图 - 频道管理 - 需要登录
class ChannelView(ModelView):
    def is_accessible(self):
        return current_user.is_authenticated

    def inaccessible_callback(self, name, **kwargs):
        return redirect(url_for('login'))

    column_list = ['id', 'channel_name', 'channel_title', 'channel_url', 'channel_is_enabled', 'channel_size', 'channel_tcreate']
    column_searchable_list = ['channel_name', 'channel_title', 'channel_url']
    column_filters = ['channel_is_enabled', 'channel_is_mega_group', 'channel_is_group', 'channel_is_private']
    column_editable_list = ['channel_is_enabled']
    form_excluded_columns = ['messages', 'notifications', 'accounts']
    column_labels = {
        'id': 'ID',
        'channel_name': '频道名称',
        'channel_title': '频道标题',
        'channel_url': '频道URL',
        'channel_is_enabled': '启用状态',
        'channel_size': '成员数',
        'channel_tcreate': '创建时间'
    }
    can_export = True
    page_size = 50
    list_template = 'admin/channel_list.html'

    @expose('/sync-channels/')
    def sync_channels_view(self):
        """显示频道同步页面"""
        try:
            # 获取第一个启用的账户
            account = db_session.query(Account).filter_by(account_is_enabled=True).first()
            if not account:
                flash('没有找到启用的账户', 'error')
                return redirect(url_for('.index_view'))

            # 创建 Telegram 客户端并获取频道
            channels = asyncio.run(fetch_telegram_channels(account))

            return self.render('admin/sync_channels.html', channels=channels, account=account)
        except Exception as e:
            flash(f'获取频道失败: {str(e)}', 'error')
            return redirect(url_for('.index_view'))

    @expose('/import-channels/', methods=['POST'])
    def import_channels_view(self):
        """批量导入选中的频道"""
        from flask import request

        try:
            selected_channels = request.form.getlist('channels')
            account = db_session.query(Account).filter_by(account_is_enabled=True).first()

            if not account:
                flash('没有找到启用的账户', 'error')
                return redirect(url_for('.index_view'))

            imported_count = 0
            skipped_count = 0

            for channel_data in selected_channels:
                # 解析频道数据
                parts = channel_data.split('|')
                if len(parts) < 8:
                    continue

                channel_id = int(parts[0])
                channel_name = parts[1]
                channel_title = parts[2]
                channel_url = parts[3]
                is_megagroup = parts[4] == 'True'
                is_group = parts[5] == 'True'
                is_private = parts[6] == 'True'
                is_broadcast = parts[7] == 'True'

                # 检查频道是否已存在
                existing_channel = db_session.query(Channel).filter_by(channel_id=channel_id).first()

                if existing_channel:
                    skipped_count += 1
                    continue

                # 创建新频道
                new_channel = Channel(
                    channel_id=channel_id,
                    channel_name=channel_name,
                    channel_title=channel_title,
                    channel_url=channel_url,
                    account_id=account.account_id,
                    channel_is_mega_group=is_megagroup,
                    channel_is_group=is_group,
                    channel_is_private=is_private,
                    channel_is_broadcast=is_broadcast,
                    channel_is_enabled=True,
                    channel_tcreate=datetime.now()
                )
                db_session.add(new_channel)
                db_session.flush()

                # 创建监控关系
                monitor = Monitor(
                    channel_id=new_channel.id,
                    account_id=account.account_id,
                    monitor_tcreate=datetime.now()
                )
                db_session.add(monitor)
                imported_count += 1

            db_session.commit()
            flash(f'成功导入 {imported_count} 个频道，跳过 {skipped_count} 个已存在的频道', 'success')

        except Exception as e:
            db_session.rollback()
            flash(f'导入频道失败: {str(e)}', 'error')

        return redirect(url_for('.index_view'))

    @expose('/fetch-history/<int:channel_id>/')
    def fetch_history_view(self, channel_id):
        """显示历史消息拉取页面"""
        try:
            channel = db_session.query(Channel).get(channel_id)
            if not channel:
                flash('频道不存在', 'error')
                return redirect(url_for('.index_view'))

            return self.render('admin/fetch_history.html', channel=channel)
        except Exception as e:
            flash(f'加载页面失败: {str(e)}', 'error')
            return redirect(url_for('.index_view'))

    @expose('/execute-fetch-history/', methods=['POST'])
    def execute_fetch_history_view(self):
        """执行历史消息拉取"""
        from flask import request
        import subprocess

        try:
            channel_id = request.form.get('channel_id')
            days = request.form.get('days', '7')
            limit = request.form.get('limit', '100')

            if not channel_id:
                flash('频道ID不能为空', 'error')
                return redirect(url_for('.index_view'))

            channel = db_session.query(Channel).get(channel_id)
            if not channel:
                flash('频道不存在', 'error')
                return redirect(url_for('.index_view'))

            # 构建命令
            cmd = [
                'python',
                '/app/fetch_history.py',
                '--channel-id', str(channel.channel_id),
                '--days', str(days),
                '--limit', str(limit)
            ]

            # 执行命令
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=300  # 5分钟超时
            )

            if result.returncode == 0:
                flash(f'成功拉取频道 {channel.channel_name} 的历史消息', 'success')
            else:
                error_msg = result.stderr if result.stderr else result.stdout
                flash(f'拉取历史消息失败: {error_msg}', 'error')

        except subprocess.TimeoutExpired:
            flash('拉取历史消息超时，请减少天数或限制数量', 'error')
        except Exception as e:
            flash(f'执行失败: {str(e)}', 'error')

        return redirect(url_for('.index_view'))


# 自定义模型视图 - 关键词管理
class KeywordView(ModelView):
    def is_accessible(self):
        return current_user.is_authenticated

    def inaccessible_callback(self, name, **kwargs):
        return redirect(url_for('login'))

    column_list = ['keyword_id', 'keyword_description', 'keyword_regex', 'keyword_is_enabled', 'keyword_tcreate']
    column_searchable_list = ['keyword_description', 'keyword_regex']
    column_filters = ['keyword_is_enabled']
    column_editable_list = ['keyword_is_enabled']
    form_excluded_columns = ['notifications']
    column_labels = {
        'keyword_id': 'ID',
        'keyword_description': '描述',
        'keyword_regex': '正则表达式',
        'keyword_is_enabled': '启用状态',
        'keyword_tcreate': '创建时间'
    }
    can_export = True
    page_size = 50


# 自定义模型视图 - 通知日志
class NotificationView(ModelView):
    def is_accessible(self):
        return current_user.is_authenticated

    def inaccessible_callback(self, name, **kwargs):
        return redirect(url_for('login'))

    column_list = ['id', 'keyword', 'channel', 'user', 'notification_tnotify']
    column_filters = ['notification_tnotify', 'keyword_id', 'channel_id']
    column_default_sort = ('notification_tnotify', True)  # 倒序排列（最新的在前）
    can_create = False
    can_edit = False
    can_delete = True
    column_labels = {
        'id': 'ID',
        'keyword': '关键词',
        'channel': '频道',
        'user': '用户',
        'notification_tnotify': '通知时间'
    }
    column_formatters = {
        'keyword': lambda v, c, m, p: m.keyword.keyword_description if m.keyword else 'N/A',
        'channel': lambda v, c, m, p: m.channel.channel_name if m.channel else 'N/A',
        'user': lambda v, c, m, p: m.user.chat_user_name if m.user else 'N/A',
    }
    can_export = True
    page_size = 50


# 自定义模型视图 - 消息记录
class MessageView(ModelView):
    def is_accessible(self):
        return current_user.is_authenticated

    def inaccessible_callback(self, name, **kwargs):
        return redirect(url_for('login'))

    column_list = ['message_id', 'channel', 'user', 'message_text', 'message_tcreate']
    column_searchable_list = ['message_text']
    column_filters = ['message_tcreate', 'channel_id', 'keyword_id']
    column_default_sort = ('message_tcreate', True)  # 倒序排列（最新的在前）
    can_create = False
    can_edit = False
    can_delete = True
    column_labels = {
        'message_id': 'ID',
        'channel': '频道',
        'user': '发送者',
        'message_text': '消息内容',
        'message_tcreate': '创建时间'
    }
    column_formatters = {
        'channel': lambda v, c, m, p: m.channel.channel_name if m.channel else 'N/A',
        'user': lambda v, c, m, p: m.user.chat_user_name if m.user else 'N/A',
        'message_text': lambda v, c, m, p: (m.message_text[:100] + '...') if m.message_text and len(m.message_text) > 100 else m.message_text,
    }
    can_export = True
    page_size = 50


# 自定义模型视图 - 账户管理
class AccountView(ModelView):
    def is_accessible(self):
        return current_user.is_authenticated

    def inaccessible_callback(self, name, **kwargs):
        return redirect(url_for('login'))

    column_list = ['id', 'account_user_name', 'account_phone', 'account_is_enabled', 'account_tcreate']
    column_searchable_list = ['account_user_name', 'account_phone']
    column_filters = ['account_is_enabled', 'account_is_bot', 'account_is_verified']
    column_editable_list = ['account_is_enabled']
    form_excluded_columns = ['channels', 'messages']
    column_labels = {
        'id': 'ID',
        'account_user_name': '用户名',
        'account_phone': '手机号',
        'account_is_enabled': '启用状态',
        'account_tcreate': '创建时间'
    }
    can_export = True
    page_size = 50


# 自定义模型视图 - 聊天用户
class ChatUserView(ModelView):
    def is_accessible(self):
        return current_user.is_authenticated

    def inaccessible_callback(self, name, **kwargs):
        return redirect(url_for('login'))

    column_list = ['id', 'chat_user_name', 'chat_user_phone', 'chat_user_is_bot', 'chat_user_tcreate']
    column_searchable_list = ['chat_user_name', 'chat_user_phone']
    column_filters = ['chat_user_is_bot', 'chat_user_is_verified']
    can_create = False
    can_edit = False
    form_excluded_columns = ['messages']
    column_labels = {
        'id': 'ID',
        'chat_user_name': '用户名',
        'chat_user_phone': '手机号',
        'chat_user_is_bot': '是否机器人',
        'chat_user_tcreate': '创建时间'
    }
    can_export = True
    page_size = 50


# 初始化Flask-Admin
admin = Admin(
    app,
    name='Informer管理面板',
    index_view=MyAdminIndexView()
)

# 添加模型视图
admin.add_view(ChannelView(Channel, db_session, name='频道管理', category='核心功能'))
admin.add_view(KeywordView(Keyword, db_session, name='关键词管理', category='核心功能'))
admin.add_view(NotificationView(Notification, db_session, name='通知日志', category='日志'))
admin.add_view(MessageView(Message, db_session, name='消息记录', category='日志'))
admin.add_view(AccountView(Account, db_session, name='账户管理', category='系统'))
admin.add_view(ChatUserView(ChatUser, db_session, name='聊天用户', category='系统'))

# 添加登出链接到导航栏
from flask_admin.menu import MenuLink
admin.add_link(MenuLink(name='登出', url='/logout'))


async def fetch_telegram_channels(account):
    """异步获取 Telegram 账户中的所有频道"""
    channels = []

    # 创建 session 目录
    session_dir = os.path.join(os.path.dirname(__file__), 'session')
    os.makedirs(session_dir, exist_ok=True)

    session_file = os.path.join(session_dir, account.account_phone.replace('+', ''))
    client = TelegramClient(session_file, account.account_api_id, account.account_api_hash)

    try:
        await client.connect()

        if not await client.is_user_authorized():
            return channels

        # 获取所有对话（频道、群组等）
        async for dialog in client.iter_dialogs():
            # 跳过私聊
            if dialog.is_user:
                continue

            channel_id = dialog.id

            # 移除某些频道 ID 的前缀
            if str(abs(channel_id))[:3] == '100':
                channel_id = int(str(abs(channel_id))[3:])

            channel_url = f'https://t.me/{dialog.entity.username}' if hasattr(dialog.entity, 'username') and dialog.entity.username else ''

            channels.append({
                'id': channel_id,
                'name': dialog.name,
                'title': dialog.title if hasattr(dialog, 'title') else dialog.name,
                'url': channel_url,
                'is_megagroup': getattr(dialog.entity, 'megagroup', False),
                'is_group': dialog.is_group,
                'is_private': not hasattr(dialog.entity, 'username') or not dialog.entity.username,
                'is_broadcast': getattr(dialog.entity, 'broadcast', False),
                'participants_count': getattr(dialog.entity, 'participants_count', 0)
            })

    finally:
        await client.disconnect()

    return channels


# 根路径重定向到管理面板
@app.route('/')
def index():
    return redirect('/admin')


# 登录路由
@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('admin.index'))

    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')

        if username == ADMIN_USERNAME and check_password_hash(ADMIN_PASSWORD_HASH, password):
            user = User(username)
            login_user(user)
            flash('登录成功！', 'success')
            next_page = request.args.get('next')
            return redirect(next_page or url_for('admin.index'))
        else:
            flash('用户名或密码错误', 'error')

    return render_template('login.html')


# 登出路由
@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('已成功登出', 'success')
    return redirect(url_for('login'))


if __name__ == '__main__':
    app.run(host='127.0.0.1', port=5000, debug=True)
