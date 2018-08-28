from ansible.module_utils.six import integer_types, string_types

try:
    from ansible.module_utils.http import HTTPMethod
except ImportError:
    from module_utils.http import HTTPMethod

FILE_MODEL_NAME = '_File'
SUCCESS_RESPONSE_CODE = '200'


class OperationField:
    URL = 'url'
    METHOD = 'method'
    PARAMETERS = 'parameters'
    MODEL_NAME = 'modelName'


class SpecProp:
    DEFINITIONS = 'definitions'
    OPERATIONS = 'operations'
    MODELS = 'models'


class PropName:
    ENUM = 'enum'
    TYPE = 'type'
    REQUIRED = 'required'
    INVALID_TYPE = 'invalid_type'
    REF = '$ref'
    ALL_OF = 'allOf'
    BASE_PATH = 'basePath'
    PATHS = 'paths'
    OPERATION_ID = 'operationId'
    SCHEMA = 'schema'
    ITEMS = 'items'
    PROPERTIES = 'properties'
    RESPONSES = 'responses'
    NAME = 'name'


class PropType:
    STRING = 'string'
    BOOLEAN = 'boolean'
    INTEGER = 'integer'
    NUMBER = 'number'
    OBJECT = 'object'
    ARRAY = 'array'
    FILE = 'file'


class OperationParams:
    PATH = 'path'
    QUERY = 'query'


def _get_model_name_from_url(schema_ref):
    path = schema_ref.split('/')
    return path[len(path) - 1]


class IllegalArgumentException(ValueError):
    """
    Exception raised when the function parameters:
        - not all passed
        - empty string
        - wrong type
    """
    pass


class ValidationError(ValueError):
    pass


class FdmSwaggerParser:
    _definitions = None

    def parse_spec(self, spec):
        """
        This method simplifies a swagger format and also resolves a model name for each operation
        :param spec: dict
                    expect data in the swagger format see <https://github.com/OAI/OpenAPI-Specification/blob/master/versions/2.0.md>
        :rtype: (bool, string|dict)
        :return:
        Ex.
            The models field contains model definition from swagger see <#https://github.com/OAI/OpenAPI-Specification/blob/master/versions/2.0.md#definitions>
            {
                'models':{
                    'model_name':{...},
                    ...
                },
                'operations':{
                    'operation_name':{
                        'method': 'get', #post, put, delete
                        'url': '/api/fdm/v2/object/networks', #url already contains a value from `basePath`
                        'modelName': 'NetworkObject', # it is a link to the model from 'models'
                                                      # None - for a delete operation or we don't have information
                                                      # '_File' - if an endpoint works with files
                        'parameters': {
                            'path':{
                                'param_name':{
                                    'type': 'string'#integer, boolean, number
                                    'required' True #False
                                }
                                ...
                                },
                            'query':{
                                'param_name':{
                                    'type': 'string'#integer, boolean, number
                                    'required' True #False
                                }
                                ...
                            }
                        }
                    },
                    ...
                }
            }
        """
        self._definitions = spec[SpecProp.DEFINITIONS]
        config = {
            SpecProp.MODELS: self._definitions,
            SpecProp.OPERATIONS: self._get_operations(spec)
        }
        return config

    def _get_operations(self, spec):
        base_path = spec[PropName.BASE_PATH]
        paths_dict = spec[PropName.PATHS]
        operations_dict = {}
        for url, operation_params in paths_dict.items():
            for method, params in operation_params.items():
                operation = {
                    OperationField.METHOD: method,
                    OperationField.URL: base_path + url,
                    OperationField.MODEL_NAME: self._get_model_name(method, params)
                }
                if OperationField.PARAMETERS in params:
                    operation[OperationField.PARAMETERS] = self._get_rest_params(params[OperationField.PARAMETERS])

                operation_id = params[PropName.OPERATION_ID]
                operations_dict[operation_id] = operation
        return operations_dict

    def _get_model_name(self, method, params):
        if method == HTTPMethod.GET:
            return self._get_model_name_from_responses(params)
        elif method == HTTPMethod.POST or method == HTTPMethod.PUT:
            return self._get_model_name_for_post_put_requests(params)
        else:
            return None

    def _get_model_name_for_post_put_requests(self, params):
        model_name = None
        if OperationField.PARAMETERS in params:
            body_param_dict = self._get_body_param_from_parameters(params[OperationField.PARAMETERS])
            if body_param_dict:
                schema_ref = body_param_dict[PropName.SCHEMA][PropName.REF]
                model_name = self._get_model_name_byschema_ref(schema_ref)
        if model_name is None:
            model_name = self._get_model_name_from_responses(params)
        return model_name

    @staticmethod
    def _get_body_param_from_parameters(params):
        return next((param for param in params if param['in'] == 'body'), None)

    def _get_model_name_from_responses(self, params):
        responses = params[PropName.RESPONSES]
        if SUCCESS_RESPONSE_CODE in responses:
            response = responses[SUCCESS_RESPONSE_CODE][PropName.SCHEMA]
            if PropName.REF in response:
                return self._get_model_name_byschema_ref(response[PropName.REF])
            elif PropName.PROPERTIES in response:
                ref = response[PropName.PROPERTIES][PropName.ITEMS][PropName.ITEMS][PropName.REF]
                return self._get_model_name_byschema_ref(ref)
            elif (PropName.TYPE in response) and response[PropName.TYPE] == PropType.FILE:
                return FILE_MODEL_NAME
        else:
            return None

    def _get_rest_params(self, params):
        path = {}
        query = {}
        operation_param = {
            OperationParams.PATH: path,
            OperationParams.QUERY: query
        }
        for param in params:
            in_param = param['in']
            if in_param == OperationParams.QUERY:
                query[param[PropName.NAME]] = self._simplify_param_def(param)
            elif in_param == OperationParams.PATH:
                path[param[PropName.NAME]] = self._simplify_param_def(param)
        return operation_param

    @staticmethod
    def _simplify_param_def(param):
        return {
            PropName.TYPE: param[PropName.TYPE],
            PropName.REQUIRED: param[PropName.REQUIRED]
        }

    def _get_model_name_byschema_ref(self, schema_ref):
        model_name = _get_model_name_from_url(schema_ref)
        model_def = self._definitions[model_name]
        if PropName.ALL_OF in model_def:
            return self._get_model_name_byschema_ref(model_def[PropName.ALL_OF][0][PropName.REF])
        else:
            return model_name


class FdmSwaggerValidator:
    def __init__(self, spec):
        """
        :param spec: dict
                    data from FdmSwaggerParser().parse_spec()
        """
        self._operations = spec[SpecProp.OPERATIONS]
        self._models = spec[SpecProp.MODELS]

    def validate_data(self, operation_name, data=None):
        """
        Validate data for the post|put requests
        :param operation_name: string
                            The value must be non empty string.
                            The operation name is used to get a model specification
        :param data: dict
                    The value must be in the format that the model(from operation) expects
        :rtype: (bool, string|dict)
        :return:
            (True, None) - if data valid
            Invalid:
            (False, {
                'required': [ #list of the fields that are required but were not present in the data
                    'field_name',
                    'patent.field_name',# when the nested field is omitted
                    'patent.list[2].field_name' # if data is array and one of the field is omitted
                ],
                'invalid_type':[ #list of the fields with invalid data
                        {
                           'path': 'objId', #field name or path to the field. Ex. objects[3].id, parent.name
                           'expected_type': 'string',# expected type. Ex. 'object', 'array', 'string', 'integer',
                                                     # 'boolean', 'number'
                           'actually_value': 1 # the value that user passed
                       }
                ]
            })
        :raises IllegalArgumentException
            'The operation_name parameter must be a non-empty string' if operation_name is not valid
            'The data parameter must be a dict' if data neither dict or None
            '{operation_name} operation does not support' if the spec does not contain the operation
        """
        if data is None:
            data = {}

        self._check_validate_data_params(data, operation_name)

        operation = self._operations[operation_name]
        model = self._models[operation[OperationField.MODEL_NAME]]
        status = self._init_report()

        self._validate_object(status, model, data, '')

        if len(status[PropName.REQUIRED]) > 0 or len(status[PropName.INVALID_TYPE]) > 0:
            return False, self._delete_empty_field_from_report(status)
        return True, None

    def _check_validate_data_params(self, data, operation_name):
        if not operation_name or not isinstance(operation_name, string_types):
            raise IllegalArgumentException("The operation_name parameter must be a non-empty string")
        if not isinstance(data, dict):
            raise IllegalArgumentException("The data parameter must be a dict")
        if operation_name not in self._operations:
            raise IllegalArgumentException("{0} operation does not support".format(operation_name))

    def validate_query_params(self, operation_name, params):
        """
           Validate params for the get requests. Use this method for validating the query part of the url.
           :param operation_name: string
                               The value must be non empty string.
                               The operation name is used to get a params specification
           :param params: dict
                        should be in the format that the specification(from operation) expects
                    Ex.
                    {
                        'objId': "string_value",
                        'p_integer': 1,
                        'p_boolean': True,
                        'p_number': 2.3
                    }
           :rtype:(Boolean, msg)
           :return:
               (True, None) - if params valid
               Invalid:
               (False, {
                   'required': [ #list of the fields that are required but are not present in the params
                       'field_name'
                   ],
                   'invalid_type':[ #list of the fields with invalid data and expected type of the params
                            {
                              'path': 'objId', #field name
                              'expected_type': 'string',#expected type. Ex. 'string', 'integer', 'boolean', 'number'
                              'actually_value': 1 # the value that user passed
                            }
                   ]
               })
            :raises IllegalArgumentException
               'The operation_name parameter must be a non-empty string' if operation_name is not valid
               'The params parameter must be a dict' if params neither dict or None
               '{operation_name} operation does not support' if the spec does not contain the operation
           """
        return self._validate_url_params(operation_name, params, resource=OperationParams.QUERY)

    def validate_path_params(self, operation_name, params):
        """
        Validate params for the get requests. Use this method for validating the path part of the url.
           :param operation_name: string
                               The value must be non empty string.
                               The operation name is used to get a params specification
           :param params: dict
                        should be in the format that the specification(from operation) expects

                 Ex.
                 {
                     'objId': "string_value",
                     'p_integer': 1,
                     'p_boolean': True,
                     'p_number': 2.3
                 }
        :rtype:(Boolean, msg)
        :return:
            (True, None) - if params valid
            Invalid:
            (False, {
                'required': [ #list of the fields that are required but are not present in the params
                    'field_name'
                ],
                'invalid_type':[ #list of the fields with invalid data and expected type of the params
                         {
                           'path': 'objId', #field name
                           'expected_type': 'string',#expected type. Ex. 'string', 'integer', 'boolean', 'number'
                           'actually_value': 1 # the value that user passed
                         }
                ]
            })
        :raises IllegalArgumentException
            'The operation_name parameter must be a non-empty string' if operation_name is not valid
            'The params parameter must be a dict' if params neither dict or None
            '{operation_name} operation does not support' if the spec does not contain the operation
        """
        return self._validate_url_params(operation_name, params, resource=OperationParams.PATH)

    def _validate_url_params(self, operation, params, resource):
        if params is None:
            params = {}

        self._check_validate_url_params(operation, params)

        operation = self._operations[operation]
        if OperationField.PARAMETERS in operation and resource in operation[OperationField.PARAMETERS]:
            spec = operation[OperationField.PARAMETERS][resource]
            status = self._init_report()
            self._check_url_params(status, spec, params)

            if len(status[PropName.REQUIRED]) > 0 or len(status[PropName.INVALID_TYPE]) > 0:
                return False, self._delete_empty_field_from_report(status)
            return True, None
        else:
            return True, None

    def _check_validate_url_params(self, operation, params):
        if not operation or not isinstance(operation, string_types):
            raise IllegalArgumentException("The operation_name parameter must be a non-empty string")
        if not isinstance(params, dict):
            raise IllegalArgumentException("The params parameter must be a dict")
        if operation not in self._operations:
            raise IllegalArgumentException("{0} operation does not support".format(operation))

    def _check_url_params(self, status, spec, params):
        for prop_name in spec.keys():
            prop = spec[prop_name]
            if prop[PropName.REQUIRED] and prop_name not in params:
                status[PropName.REQUIRED].append(prop_name)
                continue
            if prop_name in params:
                expected_type = prop[PropName.TYPE]
                value = params[prop_name]
                if prop_name in params and not self._is_correct_simple_types(expected_type, value):
                    self._add_invalid_type_report(status, '', prop_name, expected_type, value)

    def _validate_object(self, status, model, data, path):
        if self._is_enum(model):
            self._check_enum(status, model, data, path)
        elif self._is_object(model):
            self._check_object(status, model, data, path)

    def _is_enum(self, model):
        return self._is_string_type(model) and PropName.ENUM in model

    def _check_enum(self, status, model, value, path):
        if value not in model[PropName.ENUM]:
            self._add_invalid_type_report(status, path, '', PropName.ENUM, value)

    def _add_invalid_type_report(self, status, path, prop_name, expected_type, actually_value):
        status[PropName.INVALID_TYPE].append({
            'path': self._create_path_to_field(path, prop_name),
            'expected_type': expected_type,
            'actually_value': actually_value
        })

    def _check_object(self, status, model, data, path):
        if not isinstance(data, dict):
            self._add_invalid_type_report(status, path, '', PropType.OBJECT, data)
            return None

        self._check_required_fields(status, model[PropName.REQUIRED], data, path)

        model_properties = model[PropName.PROPERTIES]
        for prop in model_properties.keys():
            if prop in data:
                model_prop_val = model_properties[prop]
                expected_type = model_prop_val[PropName.TYPE]
                actually_value = data[prop]
                self._check_types(status, actually_value, expected_type, model_prop_val, path, prop)

    def _check_types(self, status, actually_value, expected_type, model, path, prop_name):
        if expected_type == PropType.OBJECT:
            ref_model = self._get_model_by_ref(model)

            self._validate_object(status, ref_model, actually_value,
                                  path=self._create_path_to_field(path, prop_name))
        elif expected_type == PropType.ARRAY:
            self._check_array(status, model, actually_value,
                              path=self._create_path_to_field(path, prop_name))
        elif not self._is_correct_simple_types(expected_type, actually_value):
            self._add_invalid_type_report(status, path, prop_name, expected_type, actually_value)

    def _get_model_by_ref(self, model_prop_val):
        model = _get_model_name_from_url(model_prop_val[PropName.REF])
        return self._models[model]

    def _check_required_fields(self, status, required_fields, data, path):
        missed_required_fields = [self._create_path_to_field(path, field) for field in
                                  required_fields if field not in data.keys()]
        if len(missed_required_fields) > 0:
            status[PropName.REQUIRED] += missed_required_fields

    def _check_array(self, status, model, data, path):
        if not isinstance(data, list):
            self._add_invalid_type_report(status, path, '', PropType.ARRAY, data)
        else:
            item_model = model[PropName.ITEMS]
            for i, item_data in enumerate(data):
                self._check_types(status, item_data, item_model[PropName.TYPE], item_model, "{0}[{1}]".format(path, i),
                                  '')

    @staticmethod
    def _is_correct_simple_types(expected_type, value):
        if expected_type == PropType.STRING:
            return isinstance(value, string_types)
        elif expected_type == PropType.BOOLEAN:
            return isinstance(value, bool)
        elif expected_type == PropType.INTEGER:
            return isinstance(value, integer_types) and not isinstance(value, bool)
        elif expected_type == PropType.NUMBER:
            return isinstance(value, (integer_types, float)) and not isinstance(value, bool)
        return False

    @staticmethod
    def _is_string_type(model):
        return PropName.TYPE in model and model[PropName.TYPE] == PropType.STRING

    @staticmethod
    def _init_report():
        return {
            PropName.REQUIRED: [],
            PropName.INVALID_TYPE: []
        }

    @staticmethod
    def _delete_empty_field_from_report(status):
        if not status[PropName.REQUIRED]:
            del status[PropName.REQUIRED]
        if not status[PropName.INVALID_TYPE]:
            del status[PropName.INVALID_TYPE]
        return status

    @staticmethod
    def _create_path_to_field(path='', field=''):
        separator = ''
        if path and field:
            separator = '.'
        return "{0}{1}{2}".format(path, separator, field)

    @staticmethod
    def _is_object(model):
        return PropName.TYPE in model and model[PropName.TYPE] == PropType.OBJECT