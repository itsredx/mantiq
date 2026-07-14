#include <tree_sitter/api.h>

void ts_tree_root_node_ptr(const TSTree *tree, TSNode *out_node) {
    *out_node = ts_tree_root_node(tree);
}

const char *ts_node_type_ptr(const TSNode *node) {
    return ts_node_type(*node);
}

uint32_t ts_node_child_count_ptr(const TSNode *node) {
    return ts_node_child_count(*node);
}

void ts_node_child_ptr(const TSNode *node, uint32_t index, TSNode *out_node) {
    *out_node = ts_node_child(*node, index);
}

uint32_t ts_node_start_byte_ptr(const TSNode *node) {
    return ts_node_start_byte(*node);
}

uint32_t ts_node_end_byte_ptr(const TSNode *node) {
    return ts_node_end_byte(*node);
}

bool ts_node_is_named_ptr(const TSNode *node) {
    return ts_node_is_named(*node);
}

char *ts_node_string_ptr(const TSNode *node) {
    return ts_node_string(*node);
}

const char *ts_node_field_name_for_child_ptr(const TSNode *node, uint32_t index) {
    return ts_node_field_name_for_child(*node, index);
}

void ts_node_named_child_ptr(const TSNode *node, uint32_t index, TSNode *out_node) {
    *out_node = ts_node_named_child(*node, index);
}
