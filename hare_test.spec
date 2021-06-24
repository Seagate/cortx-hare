# Copyright (c) 2020 Seagate Technology LLC and/or its Affiliates
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#
# For any questions about this software or licensing,
# please email opensource@seagate.com or cortx-questions@seagate.com.

# build number
%define h_build_num  %(test -n "$build_number" && echo "$build_number" || echo 1)

%define _python_bytecompile_errors_terminate_build 0

Summary: Hare test
Name: cortx-hare-test
Version: %{h_version}
Release: %{h_build_num}_%{h_gitrev}%{?dist}
License: Seagate
Group: Development/Tools
Source: cortx-hare-%{h_version}.tar.gz

Requires: python36
Requires: cortx-hare

%description
Seagate Hare Test Suite

%prep
%setup -qn cortx-hare

%build

%install
rm -rf %{buildroot}
mkdir -p %{buildroot}/opt/seagate/cortx/hare/libexec/
cp -rf test %{buildroot}/opt/seagate/cortx/hare/libexec/

%post
pip3 install pytest

%clean
rm -rf %{buildroot}

%files
%defattr(-,root,root,-)
/opt/seagate/cortx/hare/libexec/test/*
