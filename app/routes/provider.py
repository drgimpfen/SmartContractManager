from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_required, current_user

from app import db
from app.models import Provider
from app.forms import ProviderForm

bp = Blueprint('provider', __name__, url_prefix='/providers')


@bp.route('/', methods=['GET', 'POST'])
@bp.route('', methods=['GET', 'POST'])
@login_required
def index():
    form = ProviderForm()
    if form.validate_on_submit():
        provider = Provider(
            user_id=current_user.id,
            name=form.name.data.strip(),
            customer_number=form.customer_number.data.strip() if form.customer_number.data else None,
            email=form.email.data.strip() if form.email.data else None,
            phone=form.phone.data.strip() if form.phone.data else None,
            website=form.website.data.strip() if form.website.data else None,
            customer_portal=form.customer_portal.data.strip() if form.customer_portal.data else None,
            cancel_url=form.cancel_url.data.strip() if form.cancel_url.data else None,
        )
        db.session.add(provider)
        db.session.commit()
        flash('Provider successfully created.', 'success')
        return redirect(url_for('provider.index'))

    providers = Provider.query.filter_by(user_id=current_user.id).order_by(Provider.name.asc()).all()
    return render_template('providers.html', form=form, providers=providers)
