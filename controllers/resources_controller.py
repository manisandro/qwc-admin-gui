from collections import OrderedDict
import math
import requests
from urllib.parse import urljoin

from flask import abort, flash, redirect, render_template, request, url_for
from sqlalchemy.orm import joinedload

from .controller import Controller
from forms import ResourceForm


class ResourcesController(Controller):
    """Controller for resource model"""

    def __init__(self, app, handler):
        """Constructor

        :param Flask app: Flask application
        :param handler: Tenant config handler
        """
        super(ResourcesController, self).__init__(
            "Resource", 'resources', 'resource', 'resources', app,
            handler
        )

        # add custom routes
        base_route = self.base_route
        suffix = self.endpoint_suffix
        # delete cascaded
        app.add_url_rule(
            '/%s/<int:id>/cascaded' % base_route,
            'destroy_cascaded_%s' % suffix,
            self.destroy_casacaded, methods=['DELETE', 'POST']
        )
        # resource hierarchy
        app.add_url_rule(
            '/%s/<int:id>/hierarchy' % base_route, 'hierarchy_%s' % suffix,
            self.hierarchy, methods=['GET']
        )
        # import maps
        app.add_url_rule(
            '/%s/import_maps' % base_route, 'import_maps_%s' % suffix,
            self.import_maps, methods=['POST']
        )
        # import resource children
        app.add_url_rule(
            '/%s/<int:id>/import_children' % base_route,
            'import_children_%s' % suffix,
            self.import_children, methods=['POST']
        )

    def resources_for_index_query(self, search_text, resource_type, session):
        """Return query for resources list filtered by resource type.

        :param str search_text: Search string for filtering
        :param str resource_type: Optional resource type filter
        :param Session session: DB session
        """
        query = session.query(self.Resource) \
            .join(self.Resource.resource_types) \
            .order_by(self.ResourceType.list_order, self.Resource.type,
                      self.Resource.name, self.Resource.id)

        if search_text:
            query = query.filter(
                self.Resource.name.ilike("%%%s%%" % search_text)
            )

        if resource_type is not None:
            # filter by resource type
            query = query.filter(self.Resource.type == resource_type)

        # eager load relations
        query = query.options(joinedload(self.Resource.parent))

        return query

    def order_by_criterion(self, sort, sort_asc):
        """Return order_by criterion for sorted resources list as tuple.

        :param str sort: Column name for sorting
        :param bool sort_asc: Set to sort in ascending order
        """
        sortable_columns = {
            'id': [self.Resource.id],
            'type': [
                self.ResourceType.name, self.Resource.name, self.Resource.id
            ],
            'name': [
                self.Resource.name, self.ResourceType.list_order,
                self.Resource.type, self.Resource.id
            ]
        }

        order_by = sortable_columns.get(sort)
        if order_by is not None:
            if not sort_asc:
                # sort in descending order
                order_by[0] = order_by[0].desc()
            # convert multiple columns to tuple
            order_by = tuple(order_by)

        return order_by

    def index(self):
        """Show resources list."""
        self.setup_models()

        session = self.session()

        # get resources filtered by resource type
        search_text = self.search_text_arg()
        active_resource_type = request.args.get('type')
        query = self.resources_for_index_query(
            search_text, active_resource_type, session
        )

        # order by sort args
        sort, sort_asc = self.sort_args()
        sort_param = None
        if sort is not None:
            order_by = self.order_by_criterion(sort, sort_asc)
            if order_by is not None:
                if type(order_by) is tuple:
                    # order by multiple sort columns
                    query = query.order_by(None).order_by(*order_by)
                else:
                    # order by single sort column
                    query = query.order_by(None).order_by(order_by)

                sort_param = sort
                if not sort_asc:
                    # append sort direction suffix
                    sort_param = "%s-" % sort

        # paginate
        page, per_page = self.pagination_args()
        num_pages = math.ceil(query.count() / per_page)
        resources = query.limit(per_page).offset((page - 1) * per_page).all()

        pagination = {
            'page': page,
            'num_pages': num_pages,
            'per_page': per_page,
            'per_page_options': self.PER_PAGE_OPTIONS,
            'per_page_default': self.DEFAULT_PER_PAGE,
            'params': {
                'search': search_text,
                'type': active_resource_type,
                'sort': sort_param
            }
        }

        # query resource types
        resource_types = OrderedDict()
        query = session.query(self.ResourceType) \
            .order_by(self.ResourceType.list_order, self.ResourceType.name)
        for resource_type in query.all():
            resource_types[resource_type.name] = resource_type.description

        session.close()

        return render_template(
            '%s/index.html' % self.templates_dir, resources=resources,
            endpoint_suffix=self.endpoint_suffix, pkey=self.resource_pkey(),
            search_text=search_text, pagination=pagination,
            sort=sort, sort_asc=sort_asc,
            base_route=self.base_route, resource_types=resource_types,
            active_resource_type=active_resource_type
        )

    def find_resource(self, id, session):
        """Find resource by ID.

        :param int id: Resource ID
        :param Session session: DB session
        """
        return session.query(self.Resource).filter_by(id=id).first()

    def destroy_casacaded(self, id):
        """Delete existing resource and its children.

        :param int id: Resource ID
        """
        # workaround for missing DELETE methods in HTML forms
        #   using hidden form parameter '_method'
        method = request.form.get('_method', request.method).upper()
        if method != 'DELETE':
            abort(405)

        self.setup_models()

        # find resource
        session = self.session()
        resource = self.find_resource(id, session)

        if resource is not None:
            parent_id = resource.parent_id

            try:
                # delete and commit resource and its children
                self.destroy_resource_cascaded(resource, session)
                session.commit()
                self.update_config_timestamp(session)
                flash(
                    'Resource and its children have been deleted.', 'success'
                )
            except InternalError as e:
                flash('InternalError: %s' % e.orig, 'error')
            except IntegrityError as e:
                flash('IntegrityError: %s' % e.orig, 'error')

            session.close()

            if parent_id:
                # redirect to hierarchy view of parent resource
                return redirect(url_for(
                    'hierarchy_%s' % self.endpoint_suffix, id=parent_id
                ))
            else:
                # redirect to resources list
                return redirect(url_for(self.base_route))
        else:
            # resource not found
            session.close()
            abort(404)

    def destroy_resource_cascaded(self, resource, session):
        """Recursively delete existing resource and its children in DB.

        :param object resource: Resource object
        :param Session session: DB session
        """
        # recursively delete child resources (depth first)
        for child in resource.children:
            self.destroy_resource_cascaded(child, session)

        # delete resource
        session.delete(resource)

    def create_form(self, resource=None, edit_form=False):
        """Return form with fields loaded from DB.

        :param object resource: Optional resource object
        :param bool edit_form: Set if edit form
        """
        form = ResourceForm(obj=resource)

        session = self.session()

        # query resource types
        query = session.query(self.ResourceType) \
            .order_by(self.ResourceType.list_order, self.ResourceType.name)
        resource_types = query.all()

        # query resources
        query = session.query(self.Resource) \
            .join(self.Resource.resource_types) \
            .order_by(self.ResourceType.list_order, self.Resource.type,
                      self.Resource.name)
        # eager load relations
        query = query.options(
            joinedload(self.Resource.resource_type)
        )
        resources = query.all()

        session.close()

        # set choices for type select field
        form.type.choices = [
            (t.name, t.description) for t in resource_types
        ]

        resource_type = request.args.get('type')
        if resource_type is not None:
            form.type.data = resource_type

        # set choices for parent select field
        form.parent_id.choices = [(0, "")] + [
            (r.id, "%s: %s" % (r.type, r.name)) for r in resources
        ]

        # set choices for parent select field, grouped by resource type
        current_type = None
        group = {}
        form.parent_choices = []
        for r in resources:
            if r.type != current_type:
                # add new group
                current_type = r.type
                group = {
                    'resource_type': r.type,
                    'group_label': r.resource_type.description,
                    'options': []
                }

                form.parent_choices.append(group)

            # add resource to group
            group['options'].append((r.id, r.name))

        return form

    def create_or_update_resources(self, resource, form, session):
        """Create or update resource records in DB.

        :param object resource: Optional resource object
                                (None for create)
        :param FlaskForm form: Form for resource
        :param Session session: DB session
        """
        if resource is None:
            # create new resource
            resource = self.Resource()
            session.add(resource)
        else:
            # update existing resource
            resource = resource

        # update resource
        resource.type = form.type.data
        resource.name = form.name.data

        if form.parent_id.data is not None and form.parent_id.data > 0:
            resource.parent_id = form.parent_id.data
        else:
            resource.parent_id = None

    def hierarchy(self, id):
        """Show resource hierarchy.

        :param int id: Resource ID
        """
        self.setup_models()

        # find resource
        session = self.session()
        resource = self.find_resource(id, session)

        if resource is not None:
            # get root resource
            root = resource
            parent = root.parent
            while parent is not None:
                root = parent
                parent = root.parent

            # recursively collect hierarchy
            items = []
            self.collect_resources(root, 0, items, session)

            # query resource types
            resource_types = OrderedDict()
            query = session.query(self.ResourceType) \
                .order_by(self.ResourceType.list_order, self.ResourceType.name)
            for resource_type in query.all():
                resource_types[resource_type.name] = resource_type.description

            session.close()

            return render_template(
                '%s/hierarchy.html' % self.templates_dir, items=items,
                selected_item_id=resource.id,
                endpoint_suffix=self.endpoint_suffix,
                pkey=self.resource_pkey(), resource_types=resource_types
            )
        else:
            # resource not found
            session.close()
            abort(404)

    def collect_resources(self, resource, depth, items, session):
        """Recursively collect resource hierarchy from DB.

        :param object resource: Resource object
        :param int depth: Hierarchy depth
        :param list[object] choices: List of collected resources
        :param Session session: DB session
        """
        # query resource permissions
        query = session.query(self.Permission) \
            .filter(self.Permission.resource_id == resource.id)
        has_permissions = query.count() > 0

        # add resource
        items.append({
            'depth': depth,
            'resource': resource,
            'permissions': has_permissions
        })

        # get sorted children
        query = session.query(self.Resource) \
            .join(self.Resource.resource_types) \
            .order_by(self.ResourceType.list_order, self.Resource.type,
                      self.Resource.name, self.Resource.id) \
            .filter(self.Resource.parent_id == resource.id)

        # recursively collect children
        for child in query.all():
            self.collect_resources(child, depth + 1, items, session)

    def import_maps(self):
        """Import map resources."""
        # get config generator URL
        config_generator_service_url = self.handler().config().get(
            "config_generator_service_url"
        )
        if config_generator_service_url is None:
            flash('Config generator URL is not defined', 'error')
            return redirect(url_for(self.base_route))

        session = None
        try:
            # get maps for tenant from config generator service
            url = urljoin(config_generator_service_url, 'maps')
            tenant = self.handler().tenant
            response = requests.get(url, params={'tenant': tenant})
            if response.status_code != requests.codes.ok:
                self.logger.error(
                    "Could not get maps from %s:\n%s" %
                    (response.url, response.content)
                )
                flash(
                    'Could not import maps: Status %s' %
                    response.status_code, 'error'
                )
                return redirect(url_for(self.base_route))

            maps_from_config = response.json()

            self.setup_models()
            session = self.session()

            # get maps from ConfigDB
            query = session.query(self.Resource) \
                .filter(self.Resource.type == 'map')
            maps = [
                resource.name for resource in query.all()
            ]

            # add additional maps to ConfigDB
            new_maps = sorted(list(set(maps_from_config) - set(maps)))
            if new_maps:
                for map_name in new_maps:
                    # create new map resource
                    resource = self.Resource()
                    resource.type = 'map'
                    resource.name = map_name
                    session.add(resource)

                # commit resources
                session.commit()
                self.update_config_timestamp(session)

                flash(
                    '%d new maps have been added.' %
                    len(new_maps), 'success'
                )
            else:
                flash('No additional maps found.', 'info')

            session.close()

            return redirect(url_for(self.base_route, type='map'))
        except Exception as e:
            if session:
                session.close()
            msg = "Could not import maps: %s" % e
            self.logger.error(msg)
            flash(msg, 'error')
            return redirect(url_for(self.base_route))

    def import_children(self, id):
        """Import child resources for a resource:

        * Import layers for a map

        :param int id: Resource ID
        """
        self.setup_models()

        # find resource
        session = self.session()
        resource = self.find_resource(id, session)

        if resource is not None:
            # get config generator URL
            config_generator_service_url = self.handler().config().get(
                "config_generator_service_url"
            )
            if config_generator_service_url is None:
                flash('Config generator URL is not defined', 'error')
            elif resource.type == 'map':
                self.import_layers(
                    resource, config_generator_service_url, session
                )
            else:
                flash('Child import not supported for this resource type.',
                      'warning')

            session.close()

            return redirect(
                url_for('hierarchy_%s' % self.endpoint_suffix, id=id)
            )
        else:
            # resource not found
            session.close()
            abort(404)

    def import_layers(self, map_resource, config_generator_service_url,
                      session):
        """Import layers for a map.

        :param object map_resource: Map resource
        :param str config_generator_service_url: ConfigGenerator service URL
        :param Session session: DB session
        """
        try:
            # get map details from config generator service
            url = urljoin(
                config_generator_service_url, 'maps/%s' % map_resource.name
            )
            tenant = self.handler().tenant
            response = requests.get(url, params={'tenant': tenant})
            if response.status_code != requests.codes.ok:
                self.logger.error(
                    "Could not get map details from %s:\n%s" %
                    (response.url, response.content)
                )
                flash(
                    'Could not import layers: Status %s' %
                    response.status_code, 'error'
                )
                return redirect(url_for(self.base_route))

            layers_from_config = response.json().get('layers', [])

            if layers_from_config:
                # get map layers from ConfigDB
                query = session.query(self.Resource) \
                    .filter(self.Resource.type == 'layer') \
                    .filter(self.Resource.parent_id == map_resource.id)
                layers = [
                    resource.name for resource in query.all()
                ]

                # add additional layers to ConfigDB
                new_layers = sorted(
                    list(set(layers_from_config) - set(layers))
                )
                if new_layers:
                    for layer in new_layers:
                        # create new layer resource
                        resource = self.Resource()
                        resource.type = 'layer'
                        resource.name = layer
                        resource.parent_id = map_resource.id
                        session.add(resource)

                    # commit resources
                    session.commit()
                    self.update_config_timestamp(session)

                    flash(
                        '%d new layers have been added.' %
                        len(new_layers), 'success'
                    )
                else:
                    flash('No additional layers found.', 'info')
            else:
                # map not found or no layers
                flash('No layers found for this map.', 'warning')
        except Exception as e:
            msg = "Could not import layers: %s" % e
            self.logger.error(msg)
            flash(msg, 'error')
