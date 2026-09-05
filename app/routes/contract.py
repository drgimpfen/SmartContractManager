from flask import Blueprint, render_template
from flask_login import login_required

bp = Blueprint('contract', __name__, url_prefix='/contracts')

@bp.route('/')
@login_required
def index():
    return render_template('contracts.html')
