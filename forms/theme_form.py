from flask_wtf import FlaskForm
from wtforms import FieldList, FormField, BooleanField, StringField, IntegerField, TextAreaField, SubmitField
from wtforms.validators import DataRequired, Optional


class BackgroundLayersForm(FlaskForm):
    """Subform for backgroundlayers"""

    lname = StringField(validators=[DataRequired()])
    printLayer = StringField(validators=[Optional()])
    visibility = BooleanField(validators=[Optional()])


class ThemeForm(FlaskForm):
    """Main form for Theme GUI"""

    # TODO: add missing
    url = StringField("url", validators=[DataRequired()])
    title = StringField("title", validators=[Optional()])
    thumbnail = StringField("thumbnail", validators=[Optional()])
    attribution = StringField("atrribution", validators=[Optional()])
    attributionUrl = StringField("atrributionUrl", validators=[Optional()])
    format = StringField("format", validators=[Optional()])
    mapCrs = StringField("mapCrs", validators=[Optional()])
    additionalMouseCrs = StringField("additionalMouseCrs", validators=[Optional()])
    scales = TextAreaField("scales", validators=[Optional()])
    printScales = TextAreaField("printScales", validators=[Optional()])
    printResolutions = StringField("printResolutions", validators=[Optional()])
    searchProviders = StringField("searchProviders", validators=[Optional()])
    collapseLayerGroupsBelowLevel = IntegerField("collapseLayerGroupsBelowLevel", validators=[Optional()])
    default = BooleanField("default", validators=[Optional()])
    tiled = BooleanField("tiled", validators=[Optional()])
    skipEmptyFeatureAttributes = BooleanField("skipEmptyFeatureAttributes", validators=[Optional()])
    backgroundLayers = FieldList(FormField(BackgroundLayersForm))

    submit = SubmitField("submit")
