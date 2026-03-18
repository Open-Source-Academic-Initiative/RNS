import re

# Extensive Matrix of IT Lexemes (High Fidelity Architecture V2.4)
IT_KEYWORD_PATTERN = re.compile(
    r'\b('
    r'software|informátic[ao]|sistemas|computación|desarrollo web|desarrollo de software|desarrollo tecnológico|web|api|datos|programación|cloud|nube|tecnologí[ao]s de la información|tic|ciberseguridad|machine learning|hardware|'
    r'i\+d\+i|investigación aplicada|investigación y desarrollo|ciencia de datos|análisis predictivo|algoritmos|inteligencia artificial|ia|'
    r'innovación abierta|gestión tecnológica|prospectiva tecnológica|vigilancia tecnológica|transferencia de tecnología|madurez tecnológica|trl|'
    r'prototipado|mvp|prueba de concepto|poc|fábrica de software|laboratorio de innovación|sandbox|'
    r'gestión del conocimiento|propiedad intelectual|patente|derecho de autor|licenciamiento abierto|creative commons|repositorio digital|'
    r'transformación digital|hoja de ruta|roadmap tecnológico|estándares técnicos|interoperabilidad|analítica avanzada|'
    r'diseño web|página web|sitio web|portal web|e-commerce|tienda virtual|interfaz|ux/ui|'
    r'firma digital|certificado digital|biometría|identidad digital|autenticación|'
    r'consultoría especializada|asesoría técnica|apoyo a la gestión tics|arquitectura empresarial|gobierno de datos|auditoría informática|'
    r'mantenimiento preventivo|mantenimiento correctivo|soporte técnico|mesa de ayuda|help desk|reparación|'
    r'adquisición de licencias|suscripción de software|compra de equipos|suministro tecnológico|renovación tecnológica|'
    r'linux|gnu|ubuntu|debian|redhat|rhel|fedora|centos|kernel|bash|shell|terminal|'
    r'sysadmin|devops|sre|kubernetes|k8s|openshift|container|docker|podman|oci|helm|operator|cluster|node|pod|namespace|ingress|service|deployment|configmap|secret|'
    r'ci/cd|git|gitlab|github|pipeline|iac|ansible|terraform|virtualización|kvm|xen|qemu|'
    r'apache|nginx|php|python|javascript|typescript|backend|frontend|fullstack|rest|microservicios|monolito|'
    r'postgresql|mysql|mariadb|joomla|wordpress|cms|plugin|theme|template|hosting|dominio|ssl|https|dns|ldap|'
    r'yaml|json|markdown|opensource|foss|licencia|licenciamiento|gpl|mit|apache-2.0|automatización|'
    r'observabilidad|logging|monitoring|prometheus|grafana|elk|seguridad informática|seguridad de la información|seguridad digital|seguridad perimetral|seguridad de redes|hardening|firewall|selinux|apparmor|'
    r'paquete|repositorio|snap|flatpak|soluciones|aplicaciones'
    r')\b', 
    re.IGNORECASE
)
