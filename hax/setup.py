import os

from setuptools import Extension, setup


def get_mero_dir():
    d = os.environ.get('M0_SRC_DIR')
    if d:
        return d
    return os.path.normpath(os.path.dirname(os.path.abspath(__file__)) +
                            '/../../mero')


def get_mero_libs_dir():
    libs_dir = get_mero_dir() + '/mero/.libs'
    libmero = libs_dir + '/libmero.so'
    assert os.path.isfile(libmero), f'{libmero}: No such file'
    return libs_dir


setup(
    name='hax',
    version='0.0.1',
    packages=['hax'],
    setup_requires=['mypy', 'flake8'],
    install_requires=['python-consul>=1.1.0'],
    entry_points={'console_scripts': ['hax=hax.hax:main']},
    ext_modules=[
        Extension(name='libhax',
                  sources=['hax/hax.c'],
                  include_dirs=[get_mero_dir()],
                  define_macros=[('M0_INTERNAL', ''), ('M0_EXTERN', 'extern')],
                  library_dirs=[get_mero_libs_dir()],
                  runtime_library_dirs=[get_mero_libs_dir()],
                  libraries=['mero'],
                  extra_compile_args=[
                      '-g', '-Werror', '-Wall', '-Wextra', '-Wno-attributes',
                      '-Wno-unused-parameter', '-fPIC'
                  ])
    ],
)
