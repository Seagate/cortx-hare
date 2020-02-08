# build number
%define h_build_num  %(test -n "$build_number" && echo "$build_number" || echo 1)

# mero git revision
#   assume that Mero package release has format 'buildnum_gitid_kernelver'
%define h_mero_gitrev %(rpm -q --queryformat '%{RELEASE}' mero | cut -f2 -d_)

# mero version
%define h_mero_version %(rpm -q --queryformat '%{VERSION}-%{RELEASE}' mero)

# parallel build jobs
%define h_build_jobs_opt  %(test -n "$build_jobs" && echo "-j$build_jobs" || echo '')

Summary: Hare (Halon replacement)
Name: hare
Version: %{h_version}
Release: %{h_build_num}_%{h_gitrev}_m0%{h_mero_gitrev}%{?dist}
License: All rights reserved
Group: System Environment/Daemons
Source: %{name}-%{h_version}.tar.gz

BuildRequires: binutils-devel
BuildRequires: git
BuildRequires: mero
BuildRequires: mero-devel
BuildRequires: python36
BuildRequires: python36-devel
BuildRequires: python36-pip
BuildRequires: python36-setuptools

Requires: mero = %{h_mero_version}
Requires: pacemaker
Requires: pcs
Requires: python36
Requires: shyaml

Conflicts: halon

%description
Cluster monitoring and recovery for high-availability.

%prep
%setup -qn %{name}

%build
make %{?_smp_mflags}

%install
rm -rf %{buildroot}
make install DESTDIR=%{buildroot}
sed -i -e 's@^#!.*\.py3venv@#!/usr@' %{buildroot}/opt/seagate/eos/hare/bin/*

%clean
rm -rf %{buildroot}

%files
%defattr(-,root,root,-)
%{_bindir}/*
%{_exec_prefix}/lib/systemd/system/*
%{_sharedstatedir}/hare/
%{_localstatedir}/mero/hax/
/opt/seagate/eos/hare/*

%post
systemctl daemon-reload
install --directory --mode=0775 /var/lib/hare
groupadd --force hare
chgrp hare /var/lib/hare
chmod --changes g+w /var/lib/hare

%postun
systemctl daemon-reload

# Don't fail if /usr/lib/rpm/brp-python-bytecompile reports syntax errors --
# that script doesn't work with python3.
# FIXME: https://github.com/scylladb/scylla/issues/2235 suggests that proper
# fix is to rename all *.py files to *.py3.
%define _python_bytecompile_errors_terminate_build 0

# Consul binaries are stripped and don't contain build id, so rpmbuild fails
# with:
#   "ERROR: No build ID note found in consul"
%undefine _missing_build_ids_terminate_build
