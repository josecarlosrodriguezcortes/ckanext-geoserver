from ckan.lib.navl.dictization_functions import unflatten
from ckan.lib.base import (request, BaseController, model, c, response, abort)
from ckan.model.resource import Resource
import ckanext.geoserver.logic.action as action
import usginmodels
from pylons.decorators import jsonify
from ckan.logic import (tuplize_dict, clean_dict, parse_params)
from ckanext.metadata.logic import action as get_meta_action
#from ckanext.geoserver.model.Geoserver import Geoserver
from ckan.plugins import toolkit
from ckan.common import request, response
import json
import requests
import urllib
from pylons.config import config
import re

class OgcController(BaseController):
    @jsonify
    def publishOGC(self):
	"""
	Publishes the resource content into Geoserver.
	"""

	if request.method != 'POST' or not request.is_xhr:
	    return {
                'success': False,
                'message': toolkit._("Bad request - JSON Error: No request body data")
            }

	context = {'model': model, 'session': model.Session,
		'user': c.user or c.author, 'auth_user_obj': c.userobj}

	data = clean_dict(unflatten(tuplize_dict(parse_params(request.params))))

	result = {'success': False,
                  'message': toolkit._("Not enough information to publish this resource.")
            }

	resource_id = data.get("resource_id", None)
    	username = context.get("user", None)
    	package_id = data.get("package_id", None)
    	lat_field = data.get("geoserver_lat_field", None)
    	lng_field = data.get("geoserver_lng_field", None)
	state = data.get("geoserver_state_field", None)

	#get layer from package
	try:
	    md_package = None
	    pkg        = toolkit.get_action('package_show')(context, {'id': package_id})
	    extras     = pkg.get('extras', [])

            for extra in extras:
                key = extra.get('key', None)
                if key == 'md_package':
                    md_package = json.loads(extra.get('value'))
                    break

	    resourceDescription = md_package.get('resourceDescription', {})
	    layer = resourceDescription.get('usginContentModelLayer', resource_id)
	    version = resourceDescription.get('usginContentModelVersion', None)

            # handle harvested datasets that do not have a md_package
            
            if layer == resource_id and version == None:
                usgin_tag = []

                for tag in pkg['tags']:
                    if tag['name'].startswith('usgincm:'):
                        usgin_tag.append(tag['name']) 

                for key,value in (get_meta_action.get_usgin_prefix()).iteritems():
                    if reduce(lambda v1,v2: v1 or v2, map(lambda v: v in usgin_tag, value)):
                        key_arr = key.split("+")
                        break

                layer   = key_arr[1]
                version = key_arr[2] 
            
	except:
	    return result

	layer_name = data.get("layer_name", layer)
	workspace_name = state+''+layer_name

	if None in [resource_id, layer_name, username, package_id, version, state]:
	    return result

	try:
	    result = toolkit.get_action('geoserver_publish_ogc')(context, {'package_id': package_id, 'resource_id': resource_id, 'workspace_name': workspace_name, 'layer_name': layer_name, 'username': username, 'col_latitude': lat_field, 'col_longitude': lng_field, 'layer_version': version})
	except:
	    return {
                'success': False,
                'message': toolkit._("An error occured while processing your request, please contact your administrator.")
            }

	return result


    """
    Controller object for rendering getCapabilities from geoserver. It removes (#name_workspace) from NamespaceURI
    before serving it to user
    """
    def getOGCServices(self):
        data = clean_dict(unflatten(tuplize_dict(parse_params(request.params))))
        url = data.get('url', None)
        workspace = data.get('workspace', None)

        #USGIN MODEL WFS Validator add ?
        if workspace:
            workspace = workspace.replace('?', '')

        request_ogc = data.get('request', None)
        obj = None

        try:
            if not request_ogc or (request_ogc and request_ogc == "GetCapabilities"):
                if url and workspace:
                    oResponse = requests.get(urllib.unquote_plus(url))

                    #Replace the (#name_workspace) from NamespaceURI
                    obj = oResponse.text.replace('#'+workspace, '')

                    #Add API URL in all links in order to make system go through it instead of hitting geoserver direclty to remove (#name_workspace) from all ogc services XML
                    siteUrl = config.get('ckan.site_url', None)

                    if siteUrl:
                        newServiceUrl = siteUrl+"/geoserver/get-ogc-services?url="
                        match = re.compile('xlink:href=[\'|"](.*?)[\'"]')
                        matches = match.findall(obj)

                        #loop through all occurrences and replace one by one to add the link API Ckan-Geoserver
                        for item in matches:
                            obj = obj.replace(item, newServiceUrl+urllib.quote_plus(item)+"&amp;workspace="+workspace, 1)

                else:
                    msg = 'An error ocurred: [Bad Request - Missing parameters]'
                    abort(400, msg)

            elif request_ogc and request_ogc == "GetFeature":
                service = data.get('service', None)
                typename = data.get('typename', None)
                version = data.get('version', None)
                maxfeatures = data.get('maxfeatures', None)
                getFeatureURL = urllib.unquote_plus(url)+"?service=%s&request=%s&typename=%s&version=%s" % (service, request_ogc, typename, version)

                if maxfeatures:
                    getFeatureURL = getFeatureURL+"&maxfeatures=%s" % maxfeatures

                oResponse = requests.get(getFeatureURL)

                #Replace the (#name_workspace) from NamespaceURI
                obj = oResponse.text.replace('#'+workspace, '')

            response.content_type = 'application/xml; charset=utf-8'
            response.headers['Content-Length'] = len(obj)
            return obj.encode('utf-8')

        except Exception, e:
            msg = 'An error ocurred: [%s]' % str(e)
            abort(500, msg)
