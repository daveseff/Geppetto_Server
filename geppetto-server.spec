Name:           geppetto_server
Version:        0.1.0
Release:        1%{?dist}
Summary:        REST config service for Geppetto agents

License:        MIT
URL:            https://github.com/daveseff/Geppetto_Server
Source0:        %{name}-%{version}.tar.gz
BuildArch:      noarch

%{!?_unitdir:%global _unitdir /usr/lib/systemd/system}
%{!?_sysusersdir:%global _sysusersdir /usr/lib/sysusers.d}
%{!?_tmpfilesdir:%global _tmpfilesdir /usr/lib/tmpfiles.d}

BuildRequires:  python3-devel
BuildRequires:  python3-rpm-macros
BuildRequires:  python3dist(hatchling)
Requires:       python3 >= 3.10
Requires:       openssl
Requires(pre):  shadow-utils
%{?systemd_requires}

%description
Geppetto Server serves host-scoped configuration bundles to Geppetto agents
over mutual TLS.

%prep
%autosetup -n %{name}-%{version}

%build
%pyproject_wheel

%install
%pyproject_install
%pyproject_save_files geppetto_server

install -d %{buildroot}%{_sysconfdir}/geppetto_server/{config,pki,csr_pending,certs}
install -d %{buildroot}%{_sysconfdir}/geppetto_server/config/{defaults,groups,hosts,templates}
install -d %{buildroot}/var/log/geppetto
install -d %{buildroot}%{_unitdir}
install -d %{buildroot}%{_sysusersdir}
install -d %{buildroot}%{_tmpfilesdir}
install -d %{buildroot}%{_datadir}/geppetto_server/scripts

install -m 0644 packaging/geppetto-server.env %{buildroot}%{_sysconfdir}/geppetto_server/geppetto-server.env
install -m 0644 packaging/systemd/geppetto-server.service %{buildroot}%{_unitdir}/geppetto-server.service
install -m 0644 packaging/sysusers.d/geppetto-server.conf %{buildroot}%{_sysusersdir}/geppetto-server.conf
install -m 0644 packaging/tmpfiles.d/geppetto-server.conf %{buildroot}%{_tmpfilesdir}/geppetto-server.conf
install -m 0755 scripts/generate_certs.sh %{buildroot}%{_datadir}/geppetto_server/scripts/generate_certs.sh
install -m 0755 scripts/sign_csr.sh %{buildroot}%{_datadir}/geppetto_server/scripts/sign_csr.sh

%pre
getent group geppetto-server >/dev/null || groupadd -r geppetto-server
getent passwd geppetto-server >/dev/null || \
    useradd -r -g geppetto-server -d /etc/geppetto_server -s /usr/sbin/nologin \
    -c "Geppetto Server" geppetto-server
exit 0

%post
%systemd_post geppetto-server.service
systemd-tmpfiles --create geppetto-server.conf >/dev/null 2>&1 || :

%preun
%systemd_preun geppetto-server.service

%postun
%systemd_postun_with_restart geppetto-server.service

%files -f %{pyproject_files}
%{_bindir}/geppetto-config-server
%{_unitdir}/geppetto-server.service
%{_sysusersdir}/geppetto-server.conf
%{_tmpfilesdir}/geppetto-server.conf
%{_datadir}/geppetto_server/scripts/generate_certs.sh
%{_datadir}/geppetto_server/scripts/sign_csr.sh
%dir %attr(0750,geppetto-server,geppetto-server) %{_sysconfdir}/geppetto_server
%dir %attr(0750,geppetto-server,geppetto-server) %{_sysconfdir}/geppetto_server/config
%dir %attr(0750,geppetto-server,geppetto-server) %{_sysconfdir}/geppetto_server/config/defaults
%dir %attr(0750,geppetto-server,geppetto-server) %{_sysconfdir}/geppetto_server/config/groups
%dir %attr(0750,geppetto-server,geppetto-server) %{_sysconfdir}/geppetto_server/config/hosts
%dir %attr(0750,geppetto-server,geppetto-server) %{_sysconfdir}/geppetto_server/config/templates
%dir %attr(0750,geppetto-server,geppetto-server) %{_sysconfdir}/geppetto_server/pki
%dir %attr(0750,geppetto-server,geppetto-server) %{_sysconfdir}/geppetto_server/csr_pending
%dir %attr(0750,geppetto-server,geppetto-server) %{_sysconfdir}/geppetto_server/certs
%dir /var/log/geppetto
%ghost %attr(0640,geppetto-server,geppetto-server) /var/log/geppetto/geppetto-server.log
%config(noreplace) %{_sysconfdir}/geppetto_server/geppetto-server.env
%doc README.md
%license LICENSE

%changelog
* Fri Jul 10 2026 Geppetto Maintainers <noreply@example.invalid> - 0.1.0-1
- Initial server package
