import subprocess
from managed_nagios_plugin._compat import text_type
from managed_nagios_plugin.utils import _decode_if_bytes


class OIDLookup(object):
    _normalised_oids = {}

    def get(self, oids):
        single_lookup = False
        if isinstance(oids, text_type):
            single_lookup = True
            oids = [oids]

        results = {}
        for_lookup = []
        for oid in oids:
            if oid not in self._normalised_oids:
                for_lookup.append(oid)

        if for_lookup:
            self._normalised_oids.update(self.get_normalised_oids(for_lookup))

        for oid in oids:
            results[oid] = self._normalised_oids[oid]

        if single_lookup:
            return list(results.values())[0]
        else:
            return results

    def get_normalised_oids(self, oids):
        numeric_oids = [
            oid for oid in oids
            if not oid.strip('0123456789.')
        ]
        non_numeric_oids = [
            oid for oid in oids
            if oid not in numeric_oids
        ]

        normalised = {}

        for check_oids in numeric_oids, non_numeric_oids:
            if not check_oids:
                continue
            command = ['snmptranslate']
            if check_oids != numeric_oids:
                # Search through mib tree for non numeric OIDs
                # If we do this for numeric we fail.
                # If we don't for non numeric we sometimes fail.
                command.append('-IR')

            normalised.update(
                dict(
                    zip(
                        check_oids,
                        [
                            item.strip() for item in
                            _decode_if_bytes(subprocess.check_output(
                                command + check_oids
                            )).split('\n\n')
                        ],
                    )
                )
            )

        return normalised
