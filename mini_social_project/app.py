import os
import datetime
import time
from flask import Flask, request, jsonify, render_template, redirect, url_for, session, flash, g
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from functools import wraps
import traceback # Để in traceback chi tiết

# --- Khởi tạo ứng dụng và SQLAlchemy ---
app = Flask(__name__)
app.secret_key = 'minisocial_sieu_bi_mat_va_an_toan_tuyet_doi_nhe_hihi_hiha_hoho_hahaha_hehehe' # THAY ĐỔI KEY NÀY!

# Cấu hình Database SQLite
base_dir = os.path.abspath(os.path.dirname(__file__))
db_file_path = os.path.join(base_dir, 'minisocial.db')
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + db_file_path
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
print(f"INFO: Đường dẫn file database: {db_file_path}")

db = SQLAlchemy(app)

# Cấu hình thư mục upload
AVATAR_UPLOAD_FOLDER = os.path.join(app.static_folder if app.static_folder else 'static', 'uploads', 'avatars')
POST_MEDIA_UPLOAD_FOLDER = os.path.join(app.static_folder if app.static_folder else 'static', 'uploads', 'posts_media')

app.config['AVATAR_UPLOAD_FOLDER'] = AVATAR_UPLOAD_FOLDER
app.config['POST_MEDIA_UPLOAD_FOLDER'] = POST_MEDIA_UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 25 * 1024 * 1024 # Giới hạn 25MB

ALLOWED_AVATAR_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}
ALLOWED_POST_MEDIA_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'mp4', 'mov', 'avi', 'webm'}

for folder in [AVATAR_UPLOAD_FOLDER, POST_MEDIA_UPLOAD_FOLDER]:
    if not os.path.exists(folder):
        try:
            os.makedirs(folder); print(f"INFO: Đã tạo thư mục: {folder}")
        except OSError as e:
            print(f"LỖI NGHIÊM TRỌNG: Không thể tạo thư mục {folder}: {e}. Vui lòng tạo thủ công.")

# --- Database Models ---
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(128), nullable=False)
    profile_info = db.Column(db.String(300), nullable=True, default='')
    avatar = db.Column(db.String(100), nullable=True)
    theme_preference = db.Column(db.String(20), default='light')
    posts = db.relationship('Post', backref='author', lazy='dynamic', cascade="all, delete-orphan")
    comments = db.relationship('Comment', backref='commenter', lazy=True, cascade="all, delete-orphan")

class Post(db.Model):
    __tablename__ = 'post'
    id = db.Column(db.Integer, primary_key=True)
    content = db.Column(db.Text, nullable=True)
    timestamp = db.Column(db.DateTime, index=True, default=datetime.datetime.utcnow)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    media_url = db.Column(db.String(255), nullable=True)
    media_type = db.Column(db.String(10), nullable=True) 
    comments = db.relationship('Comment', backref='parent_post', lazy='dynamic', cascade="all, delete-orphan")
    likes = db.Column(db.Integer, default=0)

class Comment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    text = db.Column(db.Text, nullable=False)
    timestamp = db.Column(db.DateTime, index=True, default=datetime.datetime.utcnow)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    post_id = db.Column(db.Integer, db.ForeignKey('post.id'), nullable=False)

# --- Global data & Custom Jinja2 Filter ---
@app.before_request
def load_global_data():
    g.current_user_avatar = None
    user_id = session.get('logged_in_user_id')
    if user_id:
        user = db.session.get(User, user_id)
        if user: g.current_user_avatar = user.avatar
    g.now = datetime.datetime.utcnow()

@app.context_processor
def inject_global_data_to_templates():
   return dict(now=g.now, current_user_avatar_from_g=g.current_user_avatar)

@app.template_filter('format_datetime')
def format_datetime_filter(value, format="%d/%m/%Y lúc %H:%M"):
    if value is None: return ""
    if isinstance(value, str):
        try: value = datetime.datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError: 
            try: value = datetime.datetime.strptime(value, '%Y-%m-%dT%H:%M:%S.%f')
            except ValueError: return value
    return value.strftime(format)

# --- Decorator & Helper functions ---
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'logged_in_user_id' not in session:
            flash('Bạn cần đăng nhập để truy cập trang này.', 'warning')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

def allowed_file(filename, allowed_extensions_set):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in allowed_extensions_set

def get_file_extension(filename):
    return filename.rsplit('.', 1)[1].lower() if '.' in filename else ''

# --- Routes Xác thực ---
@app.route('/register', methods=['GET', 'POST'])
def register():
    if 'logged_in_user_id' in session: return redirect(url_for('index'))
    if request.method == 'POST':
        username = request.form.get('username','').strip()
        password = request.form.get('password')
        if not username or not password: flash('Tên đăng nhập và mật khẩu không được để trống.', 'danger')
        elif not username.isalnum() or ' ' in username: flash('Tên đăng nhập chỉ được chứa chữ cái liền nhau và số.', 'danger')
        elif User.query.filter_by(username=username).first(): flash('Tên đăng nhập đã tồn tại.', 'danger')
        elif len(password) < 6: flash('Mật khẩu phải có ít nhất 6 ký tự.', 'danger')
        else:
            hashed_password = generate_password_hash(password)
            profile_info = f"Xin chào, tôi là {username}!"
            new_user = User(username=username, password_hash=hashed_password, profile_info=profile_info)
            try:
                db.session.add(new_user); db.session.commit()
                flash('Đăng ký thành công! Vui lòng đăng nhập.', 'success')
                return redirect(url_for('login'))
            except Exception as e:
                db.session.rollback(); flash(f'Lỗi đăng ký: {e}', 'danger'); print(f"LỖI: commit register: {e}")
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if 'logged_in_user_id' in session: return redirect(url_for('index'))
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        user = User.query.filter_by(username=username).first()
        if user and check_password_hash(user.password_hash, password):
            session['logged_in_user_id'] = user.id
            session['username'] = user.username
            session['user_theme'] = user.theme_preference
            load_global_data() 
            flash('Đăng nhập thành công!', 'success')
            return redirect(url_for('index'))
        else:
            flash('Sai tên đăng nhập hoặc mật khẩu.', 'danger')
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    session.clear(); flash('Bạn đã đăng xuất.', 'info'); return redirect(url_for('login'))

@app.route('/edit_profile', methods=['GET', 'POST'])
@login_required
def edit_profile():
    user = db.session.get(User, session['logged_in_user_id']) 
    if not user: flash("Không tìm thấy người dùng.", "danger"); return redirect(url_for('index'))
    if request.method == 'POST':
        user.profile_info = request.form.get('profile_info', user.profile_info)
        if 'avatar' in request.files:
            file = request.files['avatar']
            if file and file.filename != '':
                if allowed_file(file.filename, ALLOWED_AVATAR_EXTENSIONS):
                    if user.avatar:
                        old_avatar_path = os.path.join(app.config['AVATAR_UPLOAD_FOLDER'], user.avatar)
                        if os.path.exists(old_avatar_path):
                            try: os.remove(old_avatar_path)
                            except Exception as e_rem: print(f"WARN: Lỗi xóa avatar cũ: {e_rem}")
                    filename = secure_filename(file.filename)
                    unique_filename = f"avatar_{user.id}_{int(time.time())}{os.path.splitext(filename)[1]}"
                    try:
                        file.save(os.path.join(app.config['AVATAR_UPLOAD_FOLDER'], unique_filename))
                        user.avatar = unique_filename
                        g.current_user_avatar = user.avatar 
                        print(f"INFO: Avatar được cập nhật: {user.avatar}")
                    except Exception as e_save:
                        flash(f"Lỗi lưu avatar: {str(e_save)}", "danger")
                        print(f"LỖI: Không thể lưu avatar: {e_save}")
                else:
                    flash('Định dạng ảnh đại diện không hợp lệ.', 'danger')
        new_theme = request.form.get('theme_preference')
        if new_theme in ['light', 'dark']: user.theme_preference = new_theme; session['user_theme'] = new_theme
        try:
            db.session.commit(); flash('Thông tin cá nhân đã được cập nhật!', 'success')
            print(f"INFO: Profile user {user.username} đã cập nhật.")
        except Exception as e:
            db.session.rollback(); flash(f'Lỗi cập nhật: {str(e)}', 'danger'); print(f"LỖI: commit edit_profile: {e}")
        return redirect(url_for('profile', username=user.username))
    return render_template('edit_profile.html', current_user_profile=user)

# --- ROUTE TEST DATABASE (Giữ lại nếu bạn cần) ---
@app.route('/_internal_test/db_save_and_check')
@login_required 
def internal_test_db_save_and_check(): 
    # ... (Code route test giữ nguyên như phiên bản trước, đảm bảo nó hoạt động) ...
    return "Kiểm tra console Flask để xem kết quả test DB."


# --- Routes Chính ---
@app.route('/')
@login_required
def index():
    page = request.args.get('page', 1, type=int)
    per_page = 5 
    print(f"DEBUG [INDEX ROUTE] Trang: {page}")
    posts_pagination_obj = Post.query.order_by(Post.timestamp.desc()).paginate(page=page, per_page=per_page, error_out=False)
    actual_posts_list = posts_pagination_obj.items
    print(f"DEBUG [INDEX ROUTE] Số bài lấy cho trang này: {len(actual_posts_list)}. Tổng: {posts_pagination_obj.total}")
    return render_template('index.html', posts=actual_posts_list, pagination=posts_pagination_obj)

@app.route('/profile/<username>')
def profile(username):
    user = User.query.filter_by(username=username).first_or_404()
    page = request.args.get('page', 1, type=int)
    per_page = 10
    posts_pagination_obj = user.posts.order_by(Post.timestamp.desc()).paginate(page=page, per_page=per_page, error_out=False)
    actual_posts_list = posts_pagination_obj.items
    return render_template('profile.html', profile_user=user, posts=actual_posts_list, pagination=posts_pagination_obj)

# --- API Routes ---
@app.route('/api/posts', methods=['POST'])
@login_required
def create_post_api():
    print("\nDEBUG [API POST] ========== BẮT ĐẦU YÊU CẦU TẠO BÀI ĐĂNG MỚI ==========")
    content = request.form.get('content', '').strip()
    media_file = request.files.get('mediaFile')
    user_id = session['logged_in_user_id']
    # ... (Toàn bộ logic xử lý upload và lưu post như phiên bản trước, đã có logging) ...
    if not content and not (media_file and media_file.filename):
        return jsonify({'error': 'Bài đăng phải có nội dung hoặc file.'}), 400
    new_post = Post(content=content, user_id=user_id)
    if media_file and media_file.filename != '':
        if allowed_file(media_file.filename, ALLOWED_POST_MEDIA_EXTENSIONS):
            original_filename = secure_filename(media_file.filename)
            unique_filename = f"post_{user_id}_{int(time.time())}_{original_filename}"
            file_path = os.path.join(app.config['POST_MEDIA_UPLOAD_FOLDER'], unique_filename)
            try:
                media_file.save(file_path)
                if os.path.exists(file_path):
                    new_post.media_url = unique_filename
                    ext = get_file_extension(unique_filename)
                    if ext in ['jpg', 'jpeg', 'png', 'gif']: new_post.media_type = 'image'
                    elif ext in ['mp4', 'mov', 'avi', 'webm']: new_post.media_type = 'video'
                    else: new_post.media_type = 'unknown'
                    print(f"DEBUG [API POST] Gán cho post: media_url='{new_post.media_url}', media_type='{new_post.media_type}'")
                else: print(f"LỖI: File '{unique_filename}' KHÔNG tồn tại sau save()!")
            except Exception as e: print(f"LỖI save file: {e}"); traceback.print_exc()
        else: return jsonify({'error': 'Định dạng file không hợp lệ.'}), 400
    if not new_post.content and not new_post.media_url:
        return jsonify({'error': 'Không có nội dung hợp lệ để đăng.'}), 400
    try:
        db.session.add(new_post); db.session.commit()
        print(f"DEBUG [API POST] ĐÃ COMMIT Post ID {new_post.id}. MediaURL: '{new_post.media_url}'")
    except Exception as e:
        db.session.rollback(); print(f"LỖI commit API POST: {e}"); traceback.print_exc()
        return jsonify({'error': 'Lỗi server khi lưu bài đăng.'}), 500
    author = db.session.get(User, user_id)
    return jsonify({
        'id': new_post.id, 'content': new_post.content,
        'timestamp': new_post.timestamp.isoformat() + "Z", 'user': author.username, 'avatar': author.avatar,
        'media_url': new_post.media_url, 'media_type': new_post.media_type,
        'likes': new_post.likes, 'comments': [], 'comments_count': 0, 'success': True 
    }), 201


@app.route('/api/posts/latest', methods=['GET'])
@login_required
def get_latest_posts_api():
    print("DEBUG [API LATEST] Yêu cầu nhận bài đăng mới.")
    last_post_timestamp_str = request.args.get('since') 
    query = Post.query.order_by(Post.timestamp.desc())
    if last_post_timestamp_str:
        try:
            last_post_timestamp = datetime.datetime.fromisoformat(last_post_timestamp_str.replace("Z", "+00:00"))
            query = query.filter(Post.timestamp > last_post_timestamp)
            print(f"DEBUG [API LATEST] Lọc bài mới hơn: {last_post_timestamp_str}")
        except ValueError: return jsonify({'error': 'Invalid timestamp format'}), 400
            
    new_posts = query.limit(5).all() 
    print(f"DEBUG [API LATEST] Tìm thấy {len(new_posts)} bài mới.")
    posts_data = []
    for post in new_posts:
        comments_preview = [{'text': c.text, 'user': c.commenter.username, 'avatar': c.commenter.avatar, 'timestamp': c.timestamp.isoformat() + "Z"} 
                            for c in post.comments.order_by(Comment.timestamp.asc()).limit(2).all()] 
        posts_data.append({
            'id': post.id, 'content': post.content,
            'timestamp': post.timestamp.isoformat() + "Z", 'user': post.author.username, 'avatar': post.author.avatar,
            'media_url': post.media_url, 'media_type': post.media_type,
            'likes': post.likes, 'comments_count': post.comments.count(), 'comments_preview': comments_preview 
        })
    return jsonify(posts_data)

@app.route('/api/posts/<int:post_id>/like', methods=['POST'])
@login_required
def like_post_api(post_id):
    print(f"DEBUG [API LIKE] Yêu cầu like cho post ID: {post_id}")
    post = db.session.get(Post, post_id)
    if not post: print(f"LỖI [API LIKE] Không tìm thấy post ID {post_id}"); return jsonify({'error': 'Không tìm thấy bài đăng'}), 404
    post.likes = (post.likes or 0) + 1
    try: 
        db.session.commit(); print(f"DEBUG [API LIKE] Đã commit like cho post ID {post_id}. Likes: {post.likes}")
        return jsonify({'id': post.id, 'likes': post.likes, 'success': True})
    except Exception as e:
        db.session.rollback(); print(f"LỖI [API LIKE] commit: {e}"); traceback.print_exc()
        return jsonify({'error': 'Lỗi server khi thích bài đăng.'}), 500

@app.route('/api/posts/<int:post_id>/comment', methods=['POST'])
@login_required
def comment_on_post_api(post_id):
    print(f"\nDEBUG [API COMMENT] ========== YÊU CẦU BÌNH LUẬN CHO POST ID: {post_id} ==========")
    data = request.get_json()
    if not data: print("LỖI [API COMMENT] Không có JSON data"); return jsonify({'error': 'Yêu cầu thiếu JSON data.'}), 400
    comment_text = data.get('comment_content')
    user_id = session['logged_in_user_id']
    print(f"DEBUG [API COMMENT] UserID: {user_id}, PostID: {post_id}, Text: '{comment_text}'")
    if not comment_text or not comment_text.strip():
        print("LỖI [API COMMENT] Nội dung rỗng"); return jsonify({'error': 'Nội dung bình luận không được trống.'}), 400
    post = db.session.get(Post, post_id)
    if not post: print(f"LỖI [API COMMENT] Không tìm thấy Post ID {post_id}"); return jsonify({'error': 'Không tìm thấy bài đăng.'}), 404
    new_comment = Comment(text=comment_text, user_id=user_id, post_id=post.id)
    try:
        db.session.add(new_comment); print("DEBUG [API COMMENT] Đã add comment vào session.")
        db.session.commit(); print(f"DEBUG [API COMMENT] ĐÃ COMMIT Comment ID: {new_comment.id}")
    except Exception as e:
        db.session.rollback(); print(f"LỖI [API COMMENT] commit: {e}"); traceback.print_exc()
        return jsonify({'error': 'Lỗi server khi lưu bình luận.'}), 500
    commenter = db.session.get(User, user_id)
    response_data = {
        'id': new_comment.id, 'text': new_comment.text,
        'timestamp': new_comment.timestamp.isoformat() + "Z", 'user': commenter.username, 'avatar': commenter.avatar,
        'post_id': new_comment.post_id, 'success': True 
    }
    print(f"DEBUG [API COMMENT] Trả về: {response_data}")
    return jsonify(response_data), 201

# Lệnh tạo database
@app.cli.command('init-db')
def init_db_command():
    print(f"INFO: Chuẩn bị xóa và tạo lại database tại: {db_file_path}")
    if os.path.exists(db_file_path):
        print(f"INFO: Tìm thấy DB cũ, đang xóa: {db_file_path}")
        try: os.remove(db_file_path); print("INFO: Đã xóa DB cũ.")
        except OSError as e: print(f"LỖI: xóa DB cũ: {e}. Vui lòng xóa thủ công."); return
    else: print("INFO: Không tìm thấy DB cũ, sẽ tạo mới.")
    with app.app_context(): db.create_all()
    print('INFO: Cơ sở dữ liệu đã được khởi tạo/làm mới.')

if __name__ == '__main__':
    print("----- BẮT ĐẦU ỨNG DỤNG FLASK -----")
    if not os.path.exists(db_file_path):
        print(f"WARN: File database '{db_file_path}' không tồn tại. Sẽ được tạo bởi db.create_all().")
    else:
        print(f"INFO: File database '{db_file_path}' đã tồn tại.")
    with app.app_context():
        db.create_all() 
    print("INFO: Đã gọi db.create_all() (chỉ tạo bảng nếu chưa tồn tại).")
    print("----- Sẵn sàng chạy app.run() -----")
    app.run(debug=True, port=5000)