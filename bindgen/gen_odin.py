#-------------------------------------------------------------------------------
#   gen_odin.py
#
#   Generate Odin bindings.
#-------------------------------------------------------------------------------
import gen_ir
import re, os, shutil, sys

module_root = 'sokol-odin/src/sokol'

module_names = {
    'sg_':      'gfx',
    'sapp_':    'app',
    'sapp_sg':  'glue',
    'stm_':     'time',
    'saudio_':  'audio',
    'sgl_':     'gl',
    'sdtx_':    'debugtext',
    'sshape_':  'shape',
}

system_libs = {
    'sg_': {
        'windows': {
            'd3d11': "",
            'gl': "",
        },
        'macos': {
            'metal': '"system:Cocoa.framework","system:QuartzCore.framework","system:Metal.framework","system:MetalKit.framework"',
            'gl': '"system:Cocoa.framework","system:QuartzCore.framework","system:OpenGL.framework"'
        },
        'linux': {
            'gl': ''
        }
    },
    'sapp_': {
        'windows': {
            'd3d11': '',
            'gl': '',
        },
        'macos': {
            'metal': '"system:Cocoa.framework","system:QuartzCore.framework","system:Metal.framework","system:MetalKit.framework"',
            'gl': '"system:Cocoa.framework","system:QuartzCore.framework","system:OpenGL.framework"',
        },
        'linux': {
            'gl': '',
        }
    },
    'saudio_': {
        'windows': {
            'd3d11': '',
            'gl': '',
        },
        'macos': {
            'metal': '"system:AudioToolbox.framework"',
            'gl': '"system:AudioToolbox.framework"',
        },
        'linux': {
            'gl': '',
        }
    }
}

c_source_names = {
    'sg_':      'sokol_gfx.c',
    'sapp_':    'sokol_app.c',
    'sapp_sg':  'sokol_glue.c',
    'stm_':     'sokol_time.c',
    'saudio_':  'sokol_audio.c',
    'sgl_':     'sokol_gl.c',
    'sdtx_':    'sokol_debugtext.c',
    'sshape_':  'sokol_shape.c',
}

ignores = [
    'sdtx_printf',
    'sdtx_vprintf',
    'sg_install_trace_hooks',
    'sg_trace_hooks',
]

# NOTE: syntax for function results: "func_name.RESULT"
overrides = {
    'context':                              'ctx',  # reserved keyword
    'sapp_sgcontext':                       'sapp_sgctx',
    'sgl_deg':                              'sgl_as_degrees',
    'sgl_rad':                              'sgl_as_radians',
    'sg_context_desc.color_format':         'int',
    'sg_context_desc.depth_format':         'int',
}

prim_types = {
    'int':          'i32',
    'bool':         'b8',
    'char':         'u8',
    'int8_t':       'i8',
    'uint8_t':      'u8',
    'int16_t':      'i16',
    'uint16_t':     'u16',
    'int32_t':      'i32',
    'uint32_t':     'u32',
    'int64_t':      'i64',
    'uint64_t':     'u64',
    'float':        'f32',
    'double':       'f64',
    'uintptr_t':    'u64',
    'intptr_t':     'i64',
    'size_t':       'u64'
}

prim_defaults = {
    'int':          '0',
    'bool':         'false',
    'int8_t':       '0',
    'uint8_t':      '0',
    'int16_t':      '0',
    'uint16_t':     '0',
    'int32_t':      '0',
    'uint32_t':     '0',
    'int64_t':      '0',
    'uint64_t':     '0',
    'float':        '0.0',
    'double':       '0.0',
    'uintptr_t':    '0',
    'intptr_t':     '0',
    'size_t':       '0'
}

re_1d_array = re.compile("^(?:const )?\w*\s\*?\[\d*\]$")
re_2d_array = re.compile("^(?:const )?\w*\s\*?\[\d*\]\[\d*\]$")

struct_types = []
enum_types = []
enum_items = {}
out_lines = ''

def reset_globals():
    global struct_types
    global enum_types
    global enum_items
    global out_lines
    struct_types = []
    enum_types = []
    enum_items = {}
    out_lines = ''

def l(s):
    global out_lines
    out_lines += s + '\n'

def check_override(name, default=None):
    if name in overrides:
        return overrides[name]
    elif default is None:
        return name
    else:
        return default

def check_ignore(name):
    return name in ignores

# PREFIX_BLA_BLUB to BLA_BLUB, prefix_bla_blub to bla_blub
def as_snake_case(s, prefix):
    outp = s
    if outp.lower().startswith(prefix):
        outp = outp[len(prefix):]
    return outp

def get_odin_module_path(c_prefix):
    return f'{module_root}/{module_names[c_prefix]}'

def get_csource_path(c_prefix):
    return f'{module_root}/c/{c_source_names[c_prefix]}'

def make_odin_module_directory(c_prefix):
    path = get_odin_module_path(c_prefix)
    if not os.path.isdir(path):
        os.makedirs(path)

def as_prim_type(s):
    return prim_types[s]

# prefix_bla_blub(_t) => (dep.)Bla_Blub
def as_struct_or_enum_type(s, prefix):
    parts = s.lower().split('_')
    outp = '' if s.startswith(prefix) else f'{parts[0]}.'
    for part in parts[1:]:
        # ignore '_t' type postfix
        if (part != 't'):
            outp += part.capitalize()
            outp += '_'
    outp = outp[:-1]
    return outp

# PREFIX_ENUM_BLA_BLUB => BLA_BLUB, _PREFIX_ENUM_BLA_BLUB => BLA_BLUB
def as_enum_item_name(s):
    outp = s.lstrip('_')
    parts = outp.split('_')[2:]
    outp = '_'.join(parts)
    if outp[0].isdigit():
        outp = '_' + outp
    return outp

def enum_default_item(enum_name):
    return enum_items[enum_name][0]

def is_prim_type(s):
    return s in prim_types

def is_struct_type(s):
    return s in struct_types

def is_enum_type(s):
    return s in enum_types

def is_string_ptr(s):
    return s == "const char *"

def is_const_void_ptr(s):
    return s == "const void *"

def is_void_ptr(s):
    return s == "void *"

def is_const_prim_ptr(s):
    for prim_type in prim_types:
        if s == f"const {prim_type} *":
            return True
    return False

def is_prim_ptr(s):
    for prim_type in prim_types:
        if s == f"{prim_type} *":
            return True
    return False

def is_const_struct_ptr(s):
    for struct_type in struct_types:
        if s == f"const {struct_type} *":
            return True
    return False

def is_func_ptr(s):
    return '(*)' in s

def is_1d_array_type(s):
    return re_1d_array.match(s) is not None

def is_2d_array_type(s):
    return re_2d_array.match(s) is not None

def type_default_value(s):
    return prim_defaults[s]

def extract_array_type(s):
    return s[:s.index('[')].strip()

def extract_array_sizes(s):
    return s[s.index('['):].replace('[', ' ').replace(']', ' ').split()

def extract_ptr_type(s):
    tokens = s.split()
    if tokens[0] == 'const':
        return tokens[1]
    else:
        return tokens[0]

def map_type(type, prefix, sub_type):
    if sub_type not in ['c_arg', 'odin_arg', 'struct_field']:
        sys.exit(f"Error: map_type(): unknown sub_type '{sub_type}")
    if type == "void":
        return ""
    elif is_prim_type(type):
        if sub_type == 'odin_arg':
            # for Odin args, maps C int (32-bit) to Odin int (pointer-sized),
            # and the C bool type to Odin's bool type
            if type == 'int' or type == 'uint32_t':
                return 'int'
            elif type == 'bool':
                return 'bool'
        return as_prim_type(type)
    elif is_struct_type(type):
        return as_struct_or_enum_type(type, prefix)
    elif is_enum_type(type):
        return as_struct_or_enum_type(type, prefix)
    elif is_void_ptr(type):
        return "rawptr"
    elif is_const_void_ptr(type):
        return "rawptr"
    elif is_string_ptr(type):
        return "cstring"
    elif is_const_struct_ptr(type):
        # pass Odin struct args by value, not by pointer
        if sub_type == 'odin_arg':
            return f"{as_struct_or_enum_type(extract_ptr_type(type), prefix)}"
        else:
            return f"^{as_struct_or_enum_type(extract_ptr_type(type), prefix)}"
    elif is_prim_ptr(type):
        return f"^{as_prim_type(extract_ptr_type(type))}"
    elif is_const_prim_ptr(type):
        return f"^{as_prim_type(extract_ptr_type(type))}"
    elif is_1d_array_type(type):
        array_type = extract_array_type(type)
        array_sizes = extract_array_sizes(type)
        return f"[{array_sizes[0]}]{map_type(array_type, prefix, sub_type)}"
    elif is_2d_array_type(type):
        array_type = extract_array_type(type)
        array_sizes = extract_array_sizes(type)
        return f"[{array_sizes[0]}][{array_sizes[1]}]{map_type(array_type, prefix, sub_type)}"
    elif is_func_ptr(type):
        res_type = funcptr_result_c(type, prefix)
        res_str = '' if res_type == '' else f' -> {res_type}'
        return f'proc "c" ({funcptr_args_c(type, prefix)}){res_str}'
    else:
        sys.exit(f"Error map_type(): unknown type '{type}'")

def funcdecl_args_c(decl, prefix):
    s = ''
    func_name = decl['name']
    for param_decl in decl['params']:
        if s != '':
            s += ', '
        param_name = param_decl['name']
        param_type = check_override(f'{func_name}.{param_name}', default=param_decl['type'])
        s += f"{param_name}: {map_type(param_type, prefix, 'c_arg')}"
    return s

def funcdecl_args_odin(decl, prefix):
    s = ''
    func_name = decl['name']
    for param_decl in decl['params']:
        if s != '':
            s += ', '
        param_name = param_decl['name']
        param_type = check_override(f'{func_name}.{param_name}', default=param_decl['type'])
        s += f"{param_name}: {map_type(param_type, prefix, 'odin_arg')}"
    return s

def funcptr_args_c(field_type, prefix):
    tokens = field_type[field_type.index('(*)')+4:-1].split(',')
    s = ''
    arg_index = 0;
    for token in tokens:
        arg_type = token.strip()
        if s != '':
            s += ', '
        c_arg = map_type(arg_type, prefix, 'c_arg')
        if c_arg == '':
            return ''
        else:
            s += f'a{arg_index}: {c_arg}'
        arg_index += 1
    return s

def funcptr_result_c(field_type, prefix):
    res_type = field_type[:field_type.index('(*)')].strip()
    return map_type(res_type, prefix, 'c_arg')

def funcdecl_result_c(decl, prefix):
    func_name = decl['name']
    decl_type = decl['type']
    res_c_type = decl_type[:decl_type.index('(')].strip()
    return map_type(check_override(f'{func_name}.RESULT', default=res_c_type), prefix, 'c_arg')

def funcdecl_result_odin(decl, prefix):
    func_name = decl['name']
    decl_type = decl['type']
    res_c_type = decl_type[:decl_type.index('(')].strip()
    return map_type(check_override(f'{func_name}.RESULT', default=res_c_type), prefix, 'odin_arg')

def get_system_libs(module, platform, backend):
    if module in system_libs:
        if platform in system_libs[module]:
            if backend in system_libs[module][platform]:
                libs = system_libs[module][platform][backend]
                if libs is not '':
                    return f", {libs}"
    return ''

def gen_c_imports(inp, prefix):
    clib_prefix = f'sokol_{inp["module"]}'
    clib_import = f'{clib_prefix}_clib'
    windows_d3d11_libs = get_system_libs(prefix, 'windows', 'd3d11')
    macos_metal_libs = get_system_libs(prefix, 'macos', 'metal')
    macos_gl_libs = get_system_libs(prefix, 'macos', 'gl')
    linux_gl_libs = get_system_libs(prefix, 'linux', 'gl')
    l('when ODIN_OS == .Windows {')
    l(f'    when ODIN_DEBUG == true {{ foreign import {clib_import} {{ "{clib_prefix}_windows_x64_d3d11_debug.lib"{windows_d3d11_libs} }} }}')
    l(f'    else                    {{ foreign import {clib_import} {{ "{clib_prefix}_windows_x64_d3d11_release.lib"{windows_d3d11_libs} }} }}')
    l('}')
    l('else when ODIN_OS == .Darwin {')
    l('    when ODIN_ARCH == .arm64 {')
    l(f'        when ODIN_DEBUG == true {{ foreign import {clib_import} {{ "{clib_prefix}_macos_arm64_metal_debug.a"{macos_metal_libs} }} }}')
    l(f'        else                    {{ foreign import {clib_import} {{ "{clib_prefix}_macos_arm64_metal_release.a"{macos_metal_libs} }} }}')
    l('   } else {')
    l(f'        when ODIN_DEBUG == true {{ foreign import {clib_import} {{ "{clib_prefix}_macos_x64_metal_debug.a"{macos_gl_libs} }} }}')
    l(f'        else                    {{ foreign import {clib_import} {{ "{clib_prefix}_macos_x64_metal_release.a"{macos_gl_libs} }} }}')
    l('    }')
    l('}')
    l('else {')
    l(f'    when ODIN_DEBUG == true {{ foreign import {clib_import} {{ "{clib_prefix}_linux_x64_gl_debug.lib"{linux_gl_libs} }} }}')
    l(f'    else                    {{ foreign import {clib_import} {{ "{clib_prefix}_linux_x64_gl_release.lib"{linux_gl_libs} }} }}')
    l('}')
    l('@(default_calling_convention="c")')
    l(f"foreign {clib_import} {{")
    prefix = inp['prefix']
    for decl in inp['decls']:
        if decl['kind'] == 'func' and not decl['is_dep'] and not check_ignore(decl['name']):
            args = funcdecl_args_c(decl, prefix)
            res_type = funcdecl_result_c(decl, prefix)
            res_str = '' if res_type == '' else f'-> {res_type}'
            l(f"    {decl['name']} :: proc({args}) {res_str} ---")
    l('}')

def gen_consts(decl, prefix):
    for item in decl['items']:
        item_name = check_override(item['name'])
        l(f"{as_snake_case(item_name, prefix)} :: {item['value']};")

def gen_struct(decl, prefix):
    c_struct_name = check_override(decl['name'])
    struct_name = as_struct_or_enum_type(c_struct_name, prefix)
    l(f'{struct_name} :: struct {{')
    for field in decl['fields']:
        field_name = check_override(field['name'])
        field_type = map_type(check_override(f'{c_struct_name}.{field_name}', default=field['type']), prefix, 'struct_field')
        l(f'    {field_name} : {field_type},')
    l('};')

def gen_enum(decl, prefix):
    enum_name = check_override(decl['name'])
    l(f'{as_struct_or_enum_type(enum_name, prefix)} :: enum i32 {{')
    for item in decl['items']:
        item_name = as_enum_item_name(check_override(item['name']))
        if item_name != 'FORCE_U32':
            if 'value' in item:
                l(f"    {item_name} = {item['value']},")
            else:
                l(f"    {item_name},")
    l('};')

def gen_func(decl, prefix):
    c_func_name = decl['name']
    args = funcdecl_args_odin(decl, prefix)
    res_type = funcdecl_result_odin(decl, prefix)
    res_str = '' if res_type == '' else f'-> {res_type}'
    if res_type != funcdecl_result_c(decl, prefix):
        # cast needed for return type
        res_cast = f'cast({res_type})'
    else:
        res_cast = ''
    l(f"{as_snake_case(check_override(decl['name']), prefix)} :: proc({args}) {res_str} {{")

    # workaround for 'cannot take the pointer address of 'x' which is a procedure parameter
    for param_decl in decl['params']:
        arg_name = param_decl['name']
        arg_type = check_override(f'{c_func_name}.{arg_name}', default=param_decl['type'])
        if is_const_struct_ptr(arg_type):
            l(f'    _{arg_name} := {arg_name};')
    s = '    '
    if res_type == '':
        # void result
        s += f"{c_func_name}("
    else:
        s += f"return {res_cast}{c_func_name}("
    for i, param_decl in enumerate(decl['params']):
        if i > 0:
            s += ', '
        arg_name = param_decl['name']
        arg_type = check_override(f'{c_func_name}.{arg_name}', default=param_decl['type'])
        if is_const_struct_ptr(arg_type):
            s += f"&_{arg_name}"
        else:
            odin_arg_type = map_type(arg_type, prefix, 'odin_arg')
            c_arg_type = map_type(arg_type, prefix, 'c_arg')
            if odin_arg_type != c_arg_type:
                cast = f'cast({c_arg_type})'
            else:
                cast = ''
            s += f'{cast}{arg_name}'
    s += ');'
    l(s)
    l('}')

def gen_imports(inp, dep_prefixes):
    for dep_prefix in dep_prefixes:
        dep_module_name = module_names[dep_prefix]
        l(f'import {dep_prefix[:-1]} "../{dep_module_name}"')
    l('')

def gen_module(inp, dep_prefixes):
    pre_parse(inp)
    l('// machine generated, do not edit')
    l('')
    l(f"package sokol_{inp['module']}")
    gen_imports(inp, dep_prefixes)
    prefix = inp['prefix']
    gen_c_imports(inp, prefix)
    for decl in inp['decls']:
        if not decl['is_dep']:
            kind = decl['kind']
            if kind == 'consts':
                gen_consts(decl, prefix)
            elif not check_ignore(decl['name']):
                if kind == 'struct':
                    gen_struct(decl, prefix)
                elif kind == 'enum':
                    gen_enum(decl, prefix)
                elif kind == 'func':
                    gen_func(decl, prefix)

def pre_parse(inp):
    global struct_types
    global enum_types
    for decl in inp['decls']:
        kind = decl['kind']
        if kind == 'struct':
            struct_types.append(decl['name'])
        elif kind == 'enum':
            enum_name = decl['name']
            enum_types.append(enum_name)
            enum_items[enum_name] = []
            for item in decl['items']:
                enum_items[enum_name].append(as_enum_item_name(item['name']))

def prepare():
    print('=== Generating Odin bindings:')
    if not os.path.isdir(f'{module_root}/c'):
        os.makedirs(f'{module_root}/c')

def gen(c_header_path, c_prefix, dep_c_prefixes):
    if not c_prefix in module_names:
        print(f'  >> warning: skipping generation for {c_prefix} prefix...')
        return
    reset_globals()
    make_odin_module_directory(c_prefix)
    print(f'  {c_header_path} => {module_names[c_prefix]}')
    shutil.copyfile(c_header_path, f'{module_root}/c/{os.path.basename(c_header_path)}')
    csource_path = get_csource_path(c_prefix)
    module_name = module_names[c_prefix]
    ir = gen_ir.gen(c_header_path, csource_path, module_name, c_prefix, dep_c_prefixes)
    gen_module(ir, dep_c_prefixes)
    with open(f"{module_root}/{ir['module']}/{ir['module']}.odin", 'w', newline='\n') as f_outp:
        f_outp.write(out_lines)



