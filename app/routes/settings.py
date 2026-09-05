from flask import Blueprint, render_template
from flask_login import login_required

bp = Blueprint('settings', __name__, url_prefix='/settings')

@bp.route('/')
@login_required
def index():
    return render_template('settings.html')
