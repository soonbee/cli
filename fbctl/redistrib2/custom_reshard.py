from ask import ask, askBool, askInt

from .command import custom_migrate_slots

msg_unknown_or_master = '*** The specified node is not known or not a master, ' \
                        '' \
                        '' \
                        'please retry.'


class CustomReshard(object):
    def __init__(self, trib, slots, src_node_ids, dest_node_id, src_all,
        config):
        self.trib = trib
        self.move_slot_count = slots
        self.src_node_ids = src_node_ids
        self.dest_node_id = dest_node_id
        self.src_all = src_all
        self.config = config

    def run(self):
        while self.move_slot_count <= 0:
            self._set_slots()
        while self.dest_node_id is None:
            self._set_dest_node_id()
        if not self.src_all and len(self.src_node_ids) == 0:
            self._set_src_node_ids()
        table = self._ready_plan()
        self._show_plan(table)
        self._execute_plan(table)

    def _ready_plan(self):
        print('ready_plan')
        reshard_table = self.trib.compute_reshard_table(
            self.src_node_ids,
            self.move_slot_count)
        return reshard_table

    def _show_plan(self, table):
        print('  Ready to move %s slots' % self.move_slot_count)
        self._print_src_nodes()
        self._print_dest_node()
        print('')
        for item in table:
            node = item['node']
            name = node.info['name']
            slot_num_list = item['slot_num_list']
            for slot_num in slot_num_list:
                print('Moving slot %s from %s' % (slot_num, name))
        print('')

    def _print_src_nodes(self):
        print('  Source nodes:')
        for src_node_id in self.src_node_ids:
            print('    %s' % self.trib.get_node_by_name(
                src_node_id).info_string())

    def _print_dest_node(self):
        print('  Destination node:')
        print('    %s' % self.trib.get_node_by_name(
            self.dest_node_id).info_string())

    def _execute_plan(self, table):
        text = 'Do you want to proceed with the proposed reshard plan?'
        t = self.trib
        if askBool(text):
            dest = t.name_to_node(self.dest_node_id)
            for item in table:
                node = item['node']
                slot_num_list = item['slot_num_list']
                src = node
                slots = slot_num_list
                custom_migrate_slots(src, dest, slots)
        else:
            print('Reshard canceled')

    def _set_slots(self):
        total_slot_count = self.config['total_slot_count']
        text = 'How many slots do you want to move (from 1 to %d)?' % \
               total_slot_count
        self.move_slot_count = int(askInt(text))

    def _set_dest_node_id(self):
        text = 'What is the receiving node ID?'
        candidate = ask(text)
        if self.trib.is_exist_master_node_id(candidate):
            self.dest_node_id = candidate
        else:
            print(msg_unknown_or_master)

    def _set_src_node_ids(self):
        text = '''Please enter all the source node IDs.
  Type 'all' to use all the nodes as source nodes for the hash slots.
  Type 'done' once you entered all the source nodes IDs.'''
        while True:
            print('src node ids:', self.src_node_ids)
            candidate = ask(text)
            if candidate == 'all':
                self.src_all = True
                tmp = filter(
                    lambda x: self.dest_node_id != x.info['name'],
                    self.trib.master_nodes)
                self.src_node_ids = list(map(lambda x: x.info['name'], tmp))
                return
            elif candidate == 'done':
                return
            if self.dest_node_id == candidate or candidate in self.src_node_ids:
                print(msg_unknown_or_master)
                continue
            if self.trib.is_exist_master_node_id(candidate):
                self.src_node_ids.append(candidate)
            else:
                print(msg_unknown_or_master)
