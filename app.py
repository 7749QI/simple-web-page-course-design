from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user

app = Flask(__name__)
app.config['SECRET_KEY'] = 'super_vote_system_2026_secret_key_xyz'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///vote.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'
login_manager.login_message = "请先登录账号后再操作"

# 用户表
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(30), unique=True, nullable=False)
    password = db.Column(db.String(30), nullable=False)
    is_admin = db.Column(db.Boolean, default=False)
    # 关联留言
    messages = db.relationship('Message', backref='author', cascade='all, delete-orphan')

# 投票主题（新增is_private私有标记）
class Vote(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(120), nullable=False)
    desc = db.Column(db.Text)
    creator_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    is_private = db.Column(db.Boolean, default=False) # 私有开关
    options = db.relationship('Option', backref='vote', cascade='all, delete-orphan')

# 投票选项
class Option(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    content = db.Column(db.String(80), nullable=False)
    count = db.Column(db.Integer, default=0)
    vote_id = db.Column(db.Integer, db.ForeignKey('vote.id'))

# 已投票记录（限制一人一票）
class VoteRecord(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    vote_id = db.Column(db.Integer, db.ForeignKey('vote.id'))

# 留言表（新增留言板）
class Message(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    content = db.Column(db.Text, nullable=False)
    create_time = db.Column(db.DateTime, default=db.func.now())
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))

@login_manager.user_loader
def load_user(uid):
    return User.query.get(int(uid))

# 首页：只展示公开投票，私有投票仅创建者自己可见
@app.route('/')
def index():
    if current_user.is_authenticated:
        # 公开投票 + 自己创建的私有投票
        public_votes = Vote.query.filter_by(is_private=False).all()
        my_private_votes = Vote.query.filter_by(is_private=True, creator_id=current_user.id).all()
        all_votes = public_votes + my_private_votes
    else:
        # 游客仅看公开投票
        all_votes = Vote.query.filter_by(is_private=False).all()
    return render_template("index.html", votes=all_votes)

# 登录
@app.route('/login', methods=["GET","POST"])
def login():
    if request.method == "POST":
        uname = request.form["username"]
        pwd = request.form["password"]
        user = User.query.filter_by(username=uname).first()
        if user and user.password == pwd:
            login_user(user, remember=False)
            flash("登录成功！", "success")
            return redirect(url_for("index"))
        flash("用户名或密码错误", "danger")
    return render_template("login.html")

# 注册
@app.route('/register', methods=["GET","POST"])
def register():
    if request.method == "POST":
        uname = request.form["username"]
        pwd = request.form["password"]
        if User.query.filter_by(username=uname).first():
            flash("用户名已存在", "danger")
            return redirect(url_for("register"))
        new_user = User(username=uname, password=pwd)
        db.session.add(new_user)
        db.session.commit()
        flash("注册完成，请登录", "success")
        return redirect(url_for("login"))
    return render_template("register.html")

# 退出登录
@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash("已安全退出", "info")
    return redirect(url_for("index"))

# 创建投票（新增私有勾选框逻辑）
@app.route('/create', methods=["GET","POST"])
@login_required
def create_vote():
    if request.method == "POST":
        title = request.form["title"]
        desc = request.form["desc"]
        is_private = True if request.form.get("is_private") else False
        opts = request.form.getlist("option")
        new_vote = Vote(title=title, desc=desc, creator_id=current_user.id, is_private=is_private)
        db.session.add(new_vote)
        db.session.flush()
        for opt in opts:
            if opt.strip():
                o = Option(content=opt.strip(), vote_id=new_vote.id)
                db.session.add(o)
        db.session.commit()
        flash("投票创建成功", "success")
        return redirect(url_for("index"))
    return render_template("create_vote.html")

# 投票详情页
@app.route('/vote/<int:vid>', methods=["GET","POST"])
@login_required
def vote_detail(vid):
    vote = Vote.query.get_or_404(vid)
    # 私有投票拦截：非创建者禁止访问
    if vote.is_private and vote.creator_id != current_user.id:
        flash("该投票为私有，你无权查看", "danger")
        return redirect(url_for("index"))
    # 判断是否已经投过
    record = VoteRecord.query.filter_by(user_id=current_user.id, vote_id=vid).first()
    if request.method == "POST" and not record:
        opt_id = request.form["opt"]
        opt = Option.query.get(opt_id)
        opt.count += 1
        rec = VoteRecord(user_id=current_user.id, vote_id=vid)
        db.session.add(rec)
        db.session.commit()
        flash("投票提交成功！", "success")
        return redirect(url_for("vote_detail", vid=vid))
    return render_template("vote_detail.html", vote=vote, has_voted=bool(record))

# 图表数据接口
@app.route('/chart_data/<int:vid>')
def chart_data(vid):
    vote = Vote.query.get_or_404(vid)
    # 私有投票拦截
    if vote.is_private and (not current_user.is_authenticated or vote.creator_id != current_user.id):
        return jsonify([])
    data = []
    for o in vote.options:
        data.append({"name":o.content, "value":o.count})
    return jsonify(data)

# 图表页面
@app.route('/chart/<int:vid>')
def chart_page(vid):
    vote = Vote.query.get_or_404(vid)
    # 私有投票拦截
    if vote.is_private and (not current_user.is_authenticated or vote.creator_id != current_user.id):
        flash("无权查看私有投票数据", "danger")
        return redirect(url_for("index"))
    return render_template("chart.html", vote=vote)

# 删除投票
@app.route('/del/<int:vid>')
@login_required
def del_vote(vid):
    v = Vote.query.get_or_404(vid)
    # 管理员 或 创建者可删
    if current_user.is_admin or current_user.id == v.creator_id:
        db.session.delete(v)
        db.session.commit()
        flash("投票已删除", "warning")
    else:
        flash("无删除权限", "danger")
    return redirect(url_for("index"))

# ========== 新增留言板路由 ==========
# 留言板首页
@app.route('/message')
def message_board():
    all_msg = Message.query.order_by(Message.create_time.desc()).all()
    return render_template("message.html", msg_list=all_msg)

# 发布留言
@app.route('/add_msg', methods=["POST"])
@login_required
def add_message():
    content = request.form.get("msg_content").strip()
    if not content:
        flash("留言内容不能为空", "danger")
        return redirect(url_for("message_board"))
    new_msg = Message(content=content, user_id=current_user.id)
    db.session.add(new_msg)
    db.session.commit()
    flash("留言发布成功", "success")
    return redirect(url_for("message_board"))

# 删除自己的留言
@app.route('/del_msg/<int:mid>')
@login_required
def del_message(mid):
    msg = Message.query.get_or_404(mid)
    if msg.user_id == current_user.id or current_user.is_admin:
        db.session.delete(msg)
        db.session.commit()
        flash("留言已删除", "warning")
    else:
        flash("只能删除自己的留言", "danger")
    return redirect(url_for("message_board"))

with app.app_context():
    db.create_all()

if __name__ == '__main__':
    app.run(host="0.0.0.0", port=5000, debug=True)