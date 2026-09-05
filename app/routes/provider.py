from flask import Blueprint, render_template
from flask_login import login_required

bp = Blueprint('provider', __name__, url_prefix='/providers')

@bp.route('/')
@login_required
def index():
    return render_template('providers.html')
