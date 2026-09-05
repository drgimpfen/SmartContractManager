import os
from urllib.parse import urlparse, urljoin
from flask import Flask, request, redirect, url_for, make_response
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager

from app.i18n import translate, get_locale, SUPPORTED_LOCALES, LANGUAGE_NAMES

db = SQLAlchemy()
login_manager = LoginManager()
login_manager.login_view = 'auth.login'


def is_safe_url(target):
    ref_url = urlparse(request.host_url)
    test_url = urlparse(urljoin(request.host_url, target))
    return test_url.scheme in ('http', 'https') and ref_url.netloc == test_url.netloc


def create_app(test_config=None):
    application = Flask(__name__, instance_relative_config=True)
    
    if test_config is None:
        application.config.from_mapping(
            SECRET_KEY=os.environ.get('SESSION_SECRET', 'dev_secret_key'),
            SQLALCHEMY_DATABASE_URI=os.environ.get(
                'DATABASE_URL', 
                'sqlite:///:memory:'
            ),
            SQLALCHEMY_TRACK_MODIFICATIONS=False,
            MAX_CONTENT_LENGTH=5 * 1024 * 1024 # 5 MB upload limit
        )
    else:
        application.config.from_mapping(test_config)

    db.init_app(application)
    login_manager.init_app(application)

    @application.context_processor
    def inject_i18n():
        current_loc = get_locale()
        def _(key, **kwargs):
            return translate(key, current_loc, **kwargs)
        return dict(
            _=_,
            lang=current_loc,
            languages={code: LANGUAGE_NAMES.get(code, code) for code in SUPPORTED_LOCALES}
        )

    @login_manager.user_loader
    def load_user(user_id):
        from app.models import User
        return db.session.get(User, int(user_id))

    @application.route('/set-language/<locale>')
    def set_language(locale):
        next_url = request.args.get('next') or request.referrer or url_for('dashboard.index')
        if not is_safe_url(next_url):
            next_url = url_for('dashboard.index')
        resp = make_response(redirect(next_url))
        if locale in SUPPORTED_LOCALES:
            resp.set_cookie('lang', locale, max_age=365 * 24 * 60 * 60, samesite='Lax')
        return resp

    # Register blueprints
    from app.routes import auth, dashboard, contract, provider, settings
    application.register_blueprint(auth.bp)
    application.register_blueprint(dashboard.bp)
    application.register_blueprint(contract.bp)
    application.register_blueprint(provider.bp)
    application.register_blueprint(settings.bp)

    return application
