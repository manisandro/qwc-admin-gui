import os
import json
from collections import OrderedDict

from flask import abort, flash, redirect, render_template, request, url_for
from wtforms import ValidationError
from sqlalchemy.exc import IntegrityError, InternalError

from forms import ThemeForm


class ThemesController():
    """Controller for themesconfig"""

    def __init__(self, app, config_models):
        """Constructor

        :param Flask app: Flask application
        :param ConfigModels config_models: Helper for ORM models
        """

        self.app = app
        self.config_models = config_models
        self.resources = config_models.model('resources')
        self.themesconfig = self.load_themesconfig()
        self.add_routes(app)

    def add_routes(self, app):
        """Add routes for this controller.

        :param Flask app: Flask application
        """
        # index
        app.add_url_rule(
            "/themes", "themes", self.index, methods=["GET"]
        )
        # new
        app.add_url_rule(
            "/themes/new", "new_theme", self.new_theme, methods=["GET"]
        )
        app.add_url_rule(
            "/themes/new/<int:gid>", "new_theme",
            self.new_theme, methods=["GET"]
        )
        # create
        app.add_url_rule(
            "/themes/create", "create_theme",
            self.create_theme, methods=["POST"]
        )
        app.add_url_rule(
            "/themes/create/<int:gid>", "create_theme",
            self.create_theme, methods=["POST"]
        )
        # edit
        app.add_url_rule(
            "/themes/edit/<int:tid>", "edit_theme",
            self.edit_theme, methods=["GET"]
        )
        app.add_url_rule(
            "/themes/edit/<int:tid>/<int:gid>", "edit_theme",
            self.edit_theme, methods=["GET"]
        )
        # update
        app.add_url_rule(
            "/themes/update/<int:tid>", "update_theme",
            self.update_theme, methods=["POST"]
        )
        app.add_url_rule(
            "/themes/update/<int:tid>/<int:gid>", "update_theme",
            self.update_theme, methods=["POST"]
        )
        # delete
        app.add_url_rule(
            "/themes/delete/<int:tid>", "delete_theme",
            self.delete_theme, methods=["GET"]
        )
        app.add_url_rule(
            "/themes/delete/<int:tid>/<int:gid>", "delete_theme",
            self.delete_theme, methods=["GET"]
        )
        # move
        app.add_url_rule(
            "/themes/move/<string:direction>/<int:tid>", "move_theme",
            self.move_theme, methods=["GET"]
        )
        app.add_url_rule(
            "/themes/move/<string:direction>/<int:tid>/<int:gid>",
            "move_theme", self.move_theme, methods=["GET"]
        )
        # add group
        app.add_url_rule(
            "/themes/add_theme_group", "add_theme_group",
            self.add_theme_group, methods=["GET"]
        )
        # delete group
        app.add_url_rule(
            "/themes/delete_theme_group/<int:gid>", "delete_theme_group",
            self.delete_theme_group, methods=["GET"]
        )
        # update group
        app.add_url_rule(
            "/themes/update_theme_group/<int:gid>", "update_theme_group",
            self.update_theme_group, methods=["POST"]
        )
        # move group
        app.add_url_rule(
            "/themes/move_theme_group/<string:direction>/<int:gid>",
            "move_theme_group", self.move_theme_group, methods=["GET"]
        )

    def index(self):
        """Show theme list."""
        self.themesconfig = self.load_themesconfig()
        if not self.themesconfig:
            return redirect("/")

        themes = OrderedDict()
        themes["items"] = []
        themes["groups"] = []

        if self.themesconfig.get("themes") is None:
            return

        if "items" in self.themesconfig["themes"].keys():
            for item in self.themesconfig["themes"].get("items"):
                themes["items"].append({
                    "name": item.get("title", item.get("url", ""))
                })

        if "groups" in self.themesconfig["themes"].keys():
            for group in self.themesconfig["themes"]["groups"]:
                groupEntry = {
                    "title": group.get("title", ""),
                    "items": []
                }
                for item in group["items"]:
                    groupEntry["items"].append({
                        "name": item.get("title", item.get("url", ""))
                    })
                themes["groups"].append(groupEntry)

        return render_template(
            "themes/index.html", themes=themes,
            endpoint_suffix="theme", title="Themes"
        )

    def new_theme(self, gid=None):
        """Show new theme form."""
        # use first theme as default
        if self.themesconfig["themes"]["items"]:
            default = self.themesconfig["themes"]["items"][0]
        elif self.themesconfig["themes"]["groups"] and \
                self.themesconfig["themes"]["groups"][0]["items"]:
            default = self.themesconfig["themes"]["groups"][0]["items"][0]
        else:
            default = None

        form = self.create_form(default)
        template = "themes/form.html"
        title = "Create Theme"
        action = url_for("create_theme", gid=gid)

        return render_template(
            template, title=title, form=form,
            action=action, gid=gid, method="POST"
        )

    def create_theme(self, gid=None):
        """Create new theme.

        :param int gid: group index
        """
        form = self.create_form()
        if form.validate_on_submit():
            try:
                self.create_or_update_theme(None, form, gid=gid)
                flash("Theme {0} created.".format(form.title.data), "success")
                return redirect(url_for("themes"))
            except ValidationError:
                flash("could not create theme {0}. \
                      ".format(form.title.data), "warning")
        else:
            flash("could not create theme {0}.".format(form.title.data),
                  "warning")

        # show validation errors
        template = "themes/form.html"
        title = "create theme"
        action = url_for("create_theme", gid=gid)

        return render_template(
            template, title=title, form=form,
            action=action, gid=gid, method="POST"
        )

    def edit_theme(self, tid, gid=None):
        """Show edit theme form.

        :param int tid: theme index
        :param int gid: group index
        """
        # find theme
        theme = self.find_theme(tid, gid)

        if theme is not None:
            template = "themes/form.html"
            form = self.create_form(theme)
            title = "Edit Theme"
            action = url_for("update_theme", tid=tid, gid=gid)

            return render_template(
                template, title=title, form=form, action=action,
                theme=theme, tid=tid, gid=gid, method="POST"
            )
        else:
            # theme not found
            abort(404)

    def update_theme(self, tid, gid=None):
        """Update existing theme.

        :param int tid: theme index
        :param int gid: group index
        """
        # find theme
        theme = self.find_theme(tid, gid)

        if theme is not None:
            form = self.create_form()

            if form.validate_on_submit():
                try:
                    # update theme
                    self.create_or_update_theme(theme, form, tid=tid, gid=gid)
                    flash("Updated theme {0}.".format(form.title.data),
                          "success")
                    return redirect(url_for("themes"))
                except ValidationError:
                    flash("could not update theme {0}. \
                          ".format(form.title.data), "warning")
            else:
                flash("could not update theme {0}.".format(form.title.data),
                      "warning")

            # show validation errors
            template = "themes/form.html"
            title = "Update Theme"
            action = url_for("update_theme", tid=tid, gid=gid)

            return render_template(
                template, title=title, form=form, action=action,
                tid=tid, gid=gid, method="POST"
            )

        else:
            # theme not found
            abort(404)

    def delete_theme(self, tid, gid=None):
        """Delete existing theme.

        :param int tid: theme index
        :param int gid: group index
        """
        if gid is None:
            name = self.themesconfig["themes"]["items"][tid]["url"]
            name = name.split("/")[-1]
            self.themesconfig["themes"]["items"].pop(tid)
        else:
            name = self.themesconfig["themes"]["groups"][gid]["items"][tid]["url"]
            name = name.split("/")[-1]
            self.themesconfig["themes"]["groups"][gid]["items"].pop(tid)

        # delete map resource
        session = self.config_models.session()
        resource = session.query(self.resources).filter_by(
            type="map", name=name
        ).first()

        if resource:
            try:
                session.delete(resource)
                session.commit()
            except InternalError as e:
                flash("InternalError: %s" % e.orig, "error")
            except IntegrityError:
                flash("could not delete resource map '{0}'. \
                      ".format(resource.name), "warning")

        self.save_themesconfig()
        return redirect(url_for("themes"))

    def move_theme(self, direction, tid, gid=None):
        """Delete existing theme.

        :param str direction: moving direction "up"/"down"
        :param int tid: theme index
        :param int gid: group index
        """
        if gid is None:
            items = self.themesconfig["themes"]["items"]

            if direction == "up" and tid > 0:
                items[tid - 1], items[tid] = items[tid], items[tid - 1]

            elif direction == "down" and len(items) - 1 > tid:
                items[tid], items[tid - 1] = items[tid - 1], items[tid]

            self.themesconfig["themes"]["items"] = items

        else:
            items = self.themesconfig["themes"]["groups"][gid]["items"]

            if direction == "up" and tid > 0:
                items[tid - 1], items[tid] = items[tid], items[tid - 1]

            elif direction == "down" and len(items) - 1 > tid:
                items[tid], items[tid - 1] = items[tid - 1], items[tid]

            self.themesconfig["themes"]["groups"][gid]["items"] = items

        self.save_themesconfig()
        return redirect(url_for("themes"))

    def add_theme_group(self):
        """Add new theme group."""
        self.themesconfig["themes"]["groups"].append({
            "title": "new group",
            "items": []
        })
        self.save_themesconfig()

        return redirect(url_for("themes"))

    def delete_theme_group(self, gid):
        """Delete theme group

        :param int gid: group index
        """
        self.themesconfig["themes"]["groups"].pop(gid)
        self.save_themesconfig()

        return redirect(url_for("themes"))

    def update_theme_group(self, gid):
        """Update theme group title

        :param int gid: group index
        """
        self.themesconfig["themes"]["groups"][gid]["title"] = \
            request.form["group_title"]
        self.save_themesconfig()

        return redirect(url_for("themes"))

    def move_theme_group(self, gid, direction):
        """Update theme group title

        :param int gid: group index
        :param str direction: moving direction "up"/"down"
        """
        groups = self.themesconfig["themes"]["groups"]

        if direction == "up" and gid > 1:
            groups[gid - 1], groups[gid] = groups[gid], groups[gid - 1]

        elif direction == "down" and len(groups) > gid:
            groups[gid], groups[gid - 1] = groups[gid - 1], groups[gid]

        self.themesconfig["themes"]["groups"] = groups
        self.save_themesconfig()

        return redirect(url_for("themes"))

    def find_theme(self, tid, gid=None):
        """Find theme by ID.

        :param int id: theme index
        :param int gid: group index
        """
        if gid is None:
            for i, item in enumerate(self.themesconfig["themes"]["items"]):
                if i == tid:
                    return item
        else:
            for i, group in enumerate(self.themesconfig["themes"]["groups"]):
                if i == gid:
                    for j, item in enumerate(group["items"]):
                        if j == tid:
                            return item

        return None

    def create_form(self, theme=None):
        """Return form with fields loaded from themesConfig.json.

        :param object theme: optional theme object
        """
        form = ThemeForm()

        if theme is None:
            return form
        else:
            # TODO: add missings
            form = ThemeForm(url=theme["url"])
            if "title" in theme:
                form.title.data = theme["title"]
            if "thumbnail" in theme:
                form.thumbnail.data = theme["thumbnail"]
            if "attribution" in theme:
                form.attribution.data = theme["attribution"]
            if "attributionUrl" in theme:
                form.attribution.data = theme["attributionUrl"]
            if "default" in theme:
                form.default.data = theme["default"]
            if "format" in theme:
                form.format.data = theme["format"]
            if "mapCrs" in theme:
                form.mapCrs.data = theme["mapCrs"]
            if "additionalMouseCrs" in theme:
                form.additionalMouseCrs.data = ", ".join(
                    map(str, theme["additionalMouseCrs"])
                )
            if "scales" in theme:
                form.scales.data = ", ".join(map(str, theme["scales"]))
            if "printScales" in theme:
                form.printScales.data = ", ".join(
                    map(str, theme["printScales"])
                )
            if "printResolutions" in theme:
                form.printResolutions.data = ", ".join(
                    map(str, theme["printResolutions"])
                )
            if "collapseLayerGroupsBelowLevel" in theme:
                form.skipEmptyFeatureAttributes.data = \
                        theme["collapseLayerGroupsBelowLevel"]
            if "skipEmptyFeatureAttributes" in theme:
                form.skipEmptyFeatureAttributes.data = \
                        theme["skipEmptyFeatureAttributes"]
            if "searchProviders" in theme:
                form.searchProviders.data = ", ".join(
                    map(str, theme["searchProviders"])
                )
            if "backgroundLayers" in theme:
                for layer in theme["backgroundLayers"]:
                    data = {"printLayer": "", "visibility": False}
                    data["lname"] = layer["name"]
                    if "printLayer" in layer:
                        data["printLayer"] = layer["printLayer"]
                    if "visibility" in layer:
                        data["visibility"] = layer["visibility"]
                    form.backgroundLayers.append_entry(data)

            return form

    def create_or_update_theme(self, theme, form, tid, gid=None):
        """Create or update theme records in Themesconfig.

        :param object theme: Optional theme object (None for create)
        :param FlaskForm form: Form for theme
        :param int tid: theme index
        :param int gid: group index

        """
        item = OrderedDict()
        item["url"] = form.url.data

        # TODO: add missing
        if form.title.data:
            item["title"] = form.title.data

        if form.thumbnail.data:
            item["thumbnail"] = form.thumbnail.data

        item["attribution"] = ""
        if form.attribution.data:
            item["attribution"] = form.attribution.data

        if form.attributionUrl.data:
            item["attributionUrl"] = form.attributionUrl.data

        if form.default.data:
            item["default"] = True
        else:
            item["default"] = False

        if form.format.data:
            item["format"] = form.format.data

        if form.mapCrs.data:
            item["mapCrs"] = form.mapCrs.data

        if form.additionalMouseCrs.data:
            item["additionalMouseCrs"] = form.additionalMouseCrs.data

        if form.scales.data:
            item["scales"] = list(
                map(int, form.scales.data.replace(" ", "").split(","))
            )

        if form.printScales.data:
            item["printScales"] = list(
                map(int, form.printScales.data.replace(" ", "").split(","))
            )

        if form.printResolutions.data:
            item["printResolutions"] = list(
                map(int, form.printResolutions.data.replace(" ", "").split(","))
            )

        if form.skipEmptyFeatureAttributes.data:
            item["skipEmptyFeatureAttributes"] = True
        else:
            item["skipEmptyFeatureAttributes"] = False

        if form.collapseLayerGroupsBelowLevel.data:
            item["collapseLayerGroupsBelowLevel"] = \
                form.collapseLayerGroupsBelowLevel.data

        item["searchProviders"] = []
        if form.searchProviders.data:
            item["searchProviders"] = list(
                map(str, form.searchProviders.data.replace(" ", "").split(","))
            )

        item["backgroundLayers"] = []
        if form.backgroundLayers.data:
            for layer in form.backgroundLayers.data:
                item["backgroundLayers"].append({
                    "name": layer["lname"],
                    "printLayer": layer["printLayer"],
                    "visibility": layer["visibility"]
                })

        new_name = form.url.data.split("/")[-1]
        session = self.config_models.session()

        # edit theme
        if theme:
            if gid is None:
                name = self.themesconfig["themes"]["items"][tid]["url"]
                self.themesconfig["themes"]["items"][tid] = item
            else:
                name = self.themesconfig["themes"]["groups"][gid]["items"][tid]["url"]
                self.themesconfig["themes"]["groups"][gid]["items"][tid] = item

            name = name.split("/")[-1]
            resource = session.query(self.resources).filter_by(
                name=name
            ).first()

            if resource:
                # update map resource
                resource.name = new_name
                try:
                    session.commit()
                except InternalError as e:
                    flash("InternalError: {0}".format(e.orig), "error")
                except IntegrityError:
                    flash("Could not create resource für map '{0}'! \
                          ".format(resource.name), "warning")

        # new theme
        else:
            # add map resource
            resource = self.resources()
            resource.type = "map"
            resource.name = new_name
            try:
                session.add(resource)
                session.commit()
            except InternalError as e:
                flash("InternalError: {0}".format(e.orig), "error")
            except IntegrityError:
                flash("resource for map '{0}' already exists! \
                      ".format(resource.name), "warning")

            if gid is None:
                self.themesconfig["themes"]["items"].append(item)
            else:
                self.themesconfig["themes"]["groups"][gid]["items"].append(item)

        self.save_themesconfig()

    def load_themesconfig(self):
        """Returns themesconfig as OrderedDict"""
        path = os.environ.get("QWC2_PATH", "qwc2/")
        config = os.environ.get(
            "QWC2_THEMES_CONFIG",
            path + "themesConfig.json"
        )
        try:
            with open(config, encoding='utf-8') as fh:
                return json.load(fh, object_pairs_hook=OrderedDict)
        except IOError as e:
            msg = "Could not read {}: {}".format(config, e.strerror)
            self.app.logger.error(msg)
            flash(msg, "error")
        return None

    def save_themesconfig(self):
        """Save themesconfig"""
        path = os.environ.get("QWC2_PATH", "qwc2/")
        config = os.environ.get(
            "QWC2_THEMES_CONFIG",
            path + "themesConfig.json"
        )
        try:
            with open(config, "w", encoding="utf-8") as fh:
                return json.dump(
                    self.themesconfig, fh, indent=2, separators=(',', ': ')
                )
        except IOError as e:
            msg = "Could not write {}: {}".format(config, e.strerror)
            self.app.logger.error(msg)
            flash(msg, "error")
