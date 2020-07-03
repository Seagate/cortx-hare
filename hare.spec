# build number
%define h_build_num  %(test -n "$build_number" && echo "$build_number" || echo 1)

# motr git revision
#   assume that Motr package release has format 'buildnum_gitid_kernelver'
%define h_motr_gitrev %(rpm -q --whatprovides cortx-motr | xargs rpm -q --queryformat '%{RELEASE}' | cut -f2 -d_)

# motr version
%define h_motr_version %(rpm -q --whatprovides cortx-motr | xargs rpm -q --queryformat '%{VERSION}-%{RELEASE}')

# parallel build jobs
%define h_build_jobs_opt  %(test -n "$build_jobs" && echo "-j$build_jobs" || echo '')

Summary: Hare (Halon replacement)
Name: cortx-hare
Version: %{h_version}
Release: %{h_build_num}_%{h_gitrev}%{?dist}
License: Seagate
Group: System Environment/Daemons
Source: %{name}-%{h_version}.tar.gz

BuildRequires: binutils-devel
BuildRequires: git
BuildRequires: cortx-motr
BuildRequires: cortx-motr-devel
BuildRequires: python36
BuildRequires: python36-devel
BuildRequires: python36-pip
BuildRequires: python36-setuptools

Requires: facter
Requires: jq
Requires: cortx-motr = %{h_motr_version}
Requires: python36

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
sed -i -e 's@^#!.*\.py3venv@#!/usr@' %{buildroot}/opt/seagate/cortx/hare/bin/*

%clean
rm -rf %{buildroot}

%files
%defattr(-,root,root,-)
%{_bindir}/*
%{_exec_prefix}/lib/systemd/system/*
%{_sharedstatedir}/hare/
%{_localstatedir}/motr/hax/
/opt/seagate/cortx/hare/*

%post
systemctl daemon-reload
install --directory --mode=0775 /var/lib/hare
groupadd --force hare
chgrp hare /var/lib/hare
chmod --changes g+w /var/lib/hare

# puppet-agent provides a newer version of facter, but sometimes it might not be
# available in /usr/bin/, so we need to fix this
if [[ ! -e /usr/bin/facter && -e /opt/puppetlabs/bin/facter ]] ; then
    ln -vsf /opt/puppetlabs/bin/facter /usr/bin/facter
fi

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
