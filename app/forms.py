from flask_wtf import FlaskForm
from wtforms import (
    StringField,
    PasswordField,
    SubmitField,
    SelectField,
    DateField,
    IntegerField,
    FloatField,
    TextAreaField,
    BooleanField,
)
from wtforms.validators import DataRequired, Length, Optional, NumberRange


class LoginForm(FlaskForm):
    username = StringField('Username', validators=[DataRequired(), Length(min=3, max=80)])
    password = PasswordField('Password', validators=[DataRequired(), Length(min=6)])
    submit = SubmitField('Login')


class RegisterForm(FlaskForm):
    username = StringField('Username', validators=[DataRequired(), Length(min=3, max=80)])
    password = PasswordField('Password', validators=[DataRequired(), Length(min=6)])
    submit = SubmitField('Register')


class ProviderForm(FlaskForm):
    name = StringField('Name', validators=[DataRequired(), Length(max=120)])
    customer_number = StringField('Customer Number', validators=[Optional(), Length(max=80)])
    address = TextAreaField('Address', validators=[Optional()])
    email = StringField('Email', validators=[Optional(), Length(max=120)])
    phone = StringField('Phone', validators=[Optional(), Length(max=50)])
    website = StringField('Website', validators=[Optional(), Length(max=255)])
    customer_portal = StringField('Customer Portal', validators=[Optional(), Length(max=255)])
    cancel_url = StringField('Cancellation Link', validators=[Optional(), Length(max=255)])
    submit = SubmitField('Save')


class ContractForm(FlaskForm):
    category = StringField('Category', validators=[DataRequired(), Length(max=80)])
    provider_id = SelectField('Provider', coerce=int, validators=[Optional()])
    contract_number = StringField('Contract Number', validators=[Optional(), Length(max=120)])
    start_date = DateField('Start Date', validators=[Optional()])
    end_date = DateField('End Date', validators=[Optional()])
    billing_anchor_date = DateField('Billing Anchor Date', validators=[Optional()])
    cancellation_notice_amount = IntegerField('Notice Amount', default=0, validators=[Optional(), NumberRange(min=0)])
    cancellation_notice_unit = SelectField(
        'Notice Unit',
        choices=[('days', 'Days'), ('weeks', 'Weeks'), ('months', 'Months')],
        default='days',
    )
    amount = FloatField('Amount', default=0.0, validators=[Optional(), NumberRange(min=0.0)])
    currency = StringField('Currency', default='EUR', validators=[Optional(), Length(max=8)])
    frequency = SelectField(
        'Frequency',
        choices=[
            ('monthly', 'Monthly'),
            ('quarterly', 'Quarterly'),
            ('yearly', 'Yearly'),
            ('weekly', 'Weekly'),
            ('biweekly', 'Bi-weekly'),
        ],
        default='monthly',
    )
    payment_method = StringField('Payment Method', validators=[Optional(), Length(max=64)])
    payment_term = StringField('Payment Term', validators=[Optional(), Length(max=64)])
    status = SelectField(
        'Status',
        choices=[('active', 'Active'), ('canceled', 'Canceled'), ('archived', 'Archived')],
        default='active',
    )
    tags = StringField('Tags', validators=[Optional(), Length(max=255)])
    notes = TextAreaField('Notes', validators=[Optional()])
    submit = SubmitField('Save')


class PriceEntryForm(FlaskForm):
    amount = FloatField('Amount', validators=[DataRequired(), NumberRange(min=0.0)])
    currency = StringField('Currency', default='EUR', validators=[DataRequired(), Length(max=8)])
    valid_from = DateField('Valid From', validators=[DataRequired()])
    valid_to = DateField('Valid To', validators=[Optional()])
    note = StringField('Note', validators=[Optional(), Length(max=255)])
    auto_adjust = BooleanField('Auto Adjust Overlapping Periods', default=False)
    submit = SubmitField('Save Price')
