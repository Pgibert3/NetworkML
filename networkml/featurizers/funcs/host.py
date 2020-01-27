from networkml.featurizers.features import Features

class Host(Features):


    def pyshark_ipv4(self, rows):
        new_rows = [{'IPv4': 0}]
        for row in rows:
            if 'layers' in row and '<IP Layer>' in row['layers']:
                new_rows[0]['IPv4'] = 1
        return new_rows


    def pyshark_ipv6(self, rows):
        new_rows = [{'IPv6': 0}]
        for row in rows:
            if 'layers' in row and '<IP6 Layer>' in row['layers']:
                new_rows[0]['IPv6'] = 1
        return new_rows


    def tshark_ipv4(self, rows):
        new_rows = [{'IPv4': 0}]
        for row in rows:
            if 'ip.version' in row and row['ip.version'] == '4':
                new_rows[0]['IPv4'] = 1
        return new_rows


    def tshark_ipv6(self, rows):
        new_rows = [{'IPv6': 0}]
        for row in rows:
            if 'ip.version' in row and row['ip.version'] == '6':
                new_rows[0]['IPv6'] = 1
        return new_rows


    def pyshark_layers(self, rows):
        new_rows = [{}]
        # get layers
        layers = []
        for row in rows:
            if 'layers' in row:
                temp = row['layers'].split('<')[1:]
                for t in temp:
                    layers.append(t.split(' Layer')[0])
        for layer in layers:
            new_rows[0][layer] = 1
        return new_rows
