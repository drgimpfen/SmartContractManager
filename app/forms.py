from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, SubmitField
from wtforms.validators import DataRequired, Length, Optional, Email


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
    email = StringField('Email', validators=[Optional(), Length(max=120)])
    phone = StringField('Phone', validators=[Optional(), Length(max=50)])
    website = StringField('Website', validators=[Optional(), Length(max=255)])
    customer_portal = StringField('Customer Portal', validators=[Optional(), Length(max=255)])
    cancel_url = StringField('Cancellation Link', validators=[Optional(), Length(max=255)])
    submit = SubmitField('Save')
