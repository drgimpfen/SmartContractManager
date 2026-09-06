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
    title = StringField('Title', validators=[Optional(), Length(max=120)])
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
    cancellation_target_period = SelectField(
        'Cancellation Target Period',
        choices=[
            ('exact', 'Exact / Cycle End'),
            ('end_of_month', 'End of Month'),
            ('end_of_quarter', 'End of Quarter'),
            ('end_of_year', 'End of Year (31.12.)'),
        ],
        default='exact',
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
    status = SelectField(
        'Status',
        choices=[
            ('scheduled', 'Scheduled'),
            ('active', 'Active'),
            ('pending_cancellation', 'Pending Cancellation'),
            ('cancellation_confirmed', 'Cancellation Confirmed'),
            ('paused', 'Paused'),
            ('canceled', 'Terminated'),
        ],
        default='active',
    )
    initial_term_months = IntegerField('Initial Term (Months)', default=0, validators=[Optional(), NumberRange(min=0)])
    initial_term_end_date = DateField('Initial Term End Date', validators=[Optional()])
    renewal_type = SelectField(
        'Renewal Type',
        choices=[
            ('monthly_rolling', 'Monthly Rolling (§ 309 Nr. 9 BGB)'),
            ('fixed_period', 'Fixed Period'),
            ('none', 'No Renewal (Ends on Date)'),
        ],
        default='monthly_rolling',
    )
    renewal_period_months = IntegerField('Renewal Period (Months)', default=1, validators=[Optional(), NumberRange(min=1)])
    cancellation_sent_date = DateField('Cancellation Sent Date', validators=[Optional()])
    confirmed_end_date = DateField('Confirmed End Date', validators=[Optional()])
    tags = StringField('Tags', validators=[Optional(), Length(max=255)])
    notes = TextAreaField('Notes', validators=[Optional()])
    submit = SubmitField('Save')


class ContractExtendForm(FlaskForm):
    extension_months = SelectField(
        'Extension Period',
        choices=[
            ('12', '12 Monate'),
            ('24', '24 Monate'),
            ('custom', 'Individuell (Datum)'),
        ],
        default='24',
    )
    extension_start_mode = SelectField(
        'Extension Start Mode',
        choices=[
            ('append', 'Im Anschluss an bisherige Mindestlaufzeit'),
            ('from_today', 'Ab heute neu'),
            ('custom_date', 'Freies Startdatum'),
        ],
        default='append',
    )
    custom_start_date = DateField('Custom Start Date', validators=[Optional()])
    custom_end_date = DateField('Custom End Date', validators=[Optional()])
    new_amount = FloatField('New Monthly Amount', validators=[Optional(), NumberRange(min=0.0)])
    note = TextAreaField('Note', validators=[Optional(), Length(max=1000)])
    submit = SubmitField('Extend Contract')


class PriceEntryForm(FlaskForm):
    amount = FloatField('Amount', validators=[DataRequired(), NumberRange(min=0.0)])
    currency = StringField('Currency', default='EUR', validators=[DataRequired(), Length(max=8)])
    valid_from = DateField('Valid From', validators=[DataRequired()])
    valid_to = DateField('Valid To', validators=[Optional()])
    note = StringField('Note', validators=[Optional(), Length(max=255)])
    auto_adjust = BooleanField('Auto Adjust Overlapping Periods', default=False)
    submit = SubmitField('Save Price')


class NoteForm(FlaskForm):
    content = TextAreaField('Note', validators=[DataRequired(), Length(min=1, max=5000)])
    submit = SubmitField('Add Note')
