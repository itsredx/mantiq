#include <tree_sitter/parser.h>
#include <stdio.h>
#include <wctype.h>
#include <stdint.h>
#include <stdlib.h>
#include <stdbool.h>

enum TokenType {
    INDENT,
    DEDENT,
    NEWLINE,
    DOT_NEWLINE,
};

typedef struct {
    uint16_t indent_stack[128];
    uint16_t stack_size;
    uint16_t current_line_indent;
} Scanner;

void *tree_sitter_mantiq_external_scanner_create() {
    Scanner *scanner = calloc(1, sizeof(Scanner));
    scanner->indent_stack[0] = 0;
    scanner->stack_size = 1;
    scanner->current_line_indent = 0;
    return scanner;
}

void tree_sitter_mantiq_external_scanner_destroy(void *payload) {
    free(payload);
}

unsigned tree_sitter_mantiq_external_scanner_serialize(void *payload, char *buffer) {
    Scanner *scanner = (Scanner *)payload;
    unsigned size = 0;
    buffer[size++] = (char)scanner->stack_size;
    buffer[size++] = (char)(scanner->current_line_indent & 0xFF);
    buffer[size++] = (char)((scanner->current_line_indent >> 8) & 0xFF);
    for (uint16_t i = 0; i < scanner->stack_size && size + 2 <= TREE_SITTER_SERIALIZATION_BUFFER_SIZE; i++) {
        buffer[size++] = (char)(scanner->indent_stack[i] & 0xFF);
        buffer[size++] = (char)((scanner->indent_stack[i] >> 8) & 0xFF);
    }
    return size;
}

void tree_sitter_mantiq_external_scanner_deserialize(void *payload, const char *buffer, unsigned length) {
    Scanner *scanner = (Scanner *)payload;
    if (length < 3) {
        scanner->stack_size = 1;
        scanner->indent_stack[0] = 0;
        scanner->current_line_indent = 0;
        return;
    }
    scanner->stack_size = (unsigned char)buffer[0];
    uint16_t low = (unsigned char)buffer[1];
    uint16_t high = (unsigned char)buffer[2];
    scanner->current_line_indent = low | (high << 8);
    unsigned index = 3;
    for (uint16_t i = 0; i < scanner->stack_size && index + 1 < length; i++) {
        uint16_t low_val = (unsigned char)buffer[index++];
        uint16_t high_val = (unsigned char)buffer[index++];
        scanner->indent_stack[i] = low_val | (high_val << 8);
    }
    if (scanner->stack_size == 0) {
        scanner->indent_stack[0] = 0;
        scanner->stack_size = 1;
    }
}

static void skip(TSLexer *lexer) { lexer->advance(lexer, true); }
static void advance(TSLexer *lexer) { lexer->advance(lexer, false); }

bool tree_sitter_mantiq_external_scanner_scan(void *payload, TSLexer *lexer, const bool *valid_symbols) {
    Scanner *scanner = (Scanner *)payload;

    if (lexer->eof(lexer)) {
        if (valid_symbols[DEDENT] && scanner->stack_size > 1) {
            scanner->stack_size--;
            lexer->result_symbol = DEDENT;
            return true;
        }
        return false;
    }

    uint16_t indent = 0;
    bool found_newline = false;
    uint32_t start_column = lexer->get_column(lexer);

    while (lexer->lookahead == ' ' || lexer->lookahead == '\t' || lexer->lookahead == '\f' || lexer->lookahead == '\v' ||
           lexer->lookahead == '\n' || lexer->lookahead == '\r') {
        if (lexer->lookahead == '\n' || lexer->lookahead == '\r') {
            indent = 0;
            found_newline = true;
            advance(lexer);
            lexer->mark_end(lexer);
        } else if (lexer->lookahead == ' ') {
            indent++;
            advance(lexer);
        } else if (lexer->lookahead == '\t') {
            indent += 4;
            advance(lexer);
        }
    }

    if (found_newline || start_column == 0) {
        scanner->current_line_indent = indent;
    }

    // Expression continuation: a line whose first content character is
    // '.' is a fluent-call chain broken before the dot (spec §7.2).
    // When the parser state can accept a member continuation, emit
    // DOT_NEWLINE for the newline + indentation consumed above; the
    // '.' itself is consumed into the token, which stands in for the
    // member-access dot. The valid_symbols gate keeps this inert in
    // every other context, e.g. '...' spread items inside object
    // literals, which also begin a line with a dot but are not member
    // continuations. Emitting nothing on the non-member path preserves
    // the previous INDENT/DEDENT/NEWLINE decisions verbatim.
    if (found_newline && lexer->lookahead == '.' && valid_symbols[DOT_NEWLINE]) {
        // the '.' is consumed into the DOT_NEWLINE token, which stands
        // in for the member-access dot of the continuation line
        advance(lexer);
        lexer->mark_end(lexer);
        lexer->result_symbol = DOT_NEWLINE;
        return true;
    }

    uint16_t current_indent = scanner->indent_stack[scanner->stack_size - 1];

    if (valid_symbols[DEDENT] && scanner->current_line_indent < current_indent) {
        // Slice 40: a comment-only line must not trigger the dedent
        // itself. Before this fix, a comment at lower indentation than
        // the enclosing block fired DEDENT one line early; the next
        // line's leading newline was then emitted as NEWLINE, breaking
        // `elif`/`else` chaining (E0101/E0102 cascade across the rest
        // of the file). When the would-be dedent trigger is a comment
        // at line start, skip the comment/blank lines (comments are
        // extras, so consuming them here is equivalent to the parser
        // skipping them) and re-measure from the next content line.
        // Comment-as-branch-body (deeper indent) and trailing comments
        // never enter this path and keep the original behavior.
        bool cmt_at_line_start = (start_column == 0 || start_column == indent);
        if (cmt_at_line_start && lexer->lookahead == '/') {
            lexer->mark_end(lexer);
            advance(lexer);
            if (lexer->lookahead == '/' || lexer->lookahead == '*') {
                bool is_line_comment = (lexer->lookahead == '/');
                if (is_line_comment) {
                    while (lexer->lookahead != '\n' && !lexer->eof(lexer)) {
                        advance(lexer);
                    }
                } else {
                    advance(lexer);
                    bool star = false;
                    while (!lexer->eof(lexer)) {
                        if (star && lexer->lookahead == '/') {
                            advance(lexer);
                            break;
                        }
                        star = (lexer->lookahead == '*');
                        advance(lexer);
                    }
                }
                if (is_line_comment && lexer->lookahead != '\n') {
                    // line comment ran to EOF: leave the dedent to the
                    // EOF handler on the next scan call
                    return false;
                }
                if (is_line_comment) {
                    advance(lexer);
                    lexer->mark_end(lexer);
                }
                // skip further comment/blank lines, re-measure
                for (;;) {
                    while (lexer->lookahead == ' ' || lexer->lookahead == '\t' || lexer->lookahead == '\f' || lexer->lookahead == '\v' ||
                           lexer->lookahead == '\n' || lexer->lookahead == '\r') {
                        if (lexer->lookahead == '\n' || lexer->lookahead == '\r') {
                            indent = 0;
                            found_newline = true;
                            advance(lexer);
                            lexer->mark_end(lexer);
                        } else if (lexer->lookahead == ' ') {
                            indent++;
                            advance(lexer);
                        } else if (lexer->lookahead == '\t') {
                            indent += 4;
                            advance(lexer);
                        }
                    }
                    if (found_newline && lexer->lookahead == '/') {
                        lexer->mark_end(lexer);
                        advance(lexer);
                        if (lexer->lookahead == '/') {
                            while (lexer->lookahead != '\n' && !lexer->eof(lexer)) {
                                advance(lexer);
                            }
                            if (lexer->lookahead == '\n') {
                                advance(lexer);
                                lexer->mark_end(lexer);
                                found_newline = true;
                                indent = 0;
                                continue;
                            }
                            return false;
                        } else if (lexer->lookahead == '*') {
                            advance(lexer);
                            bool star2 = false;
                            while (!lexer->eof(lexer)) {
                                if (star2 && lexer->lookahead == '/') {
                                    advance(lexer);
                                    break;
                                }
                                star2 = (lexer->lookahead == '*');
                                advance(lexer);
                            }
                            indent = 0;
                            continue;
                        }
                        // lone '/': expression continuation — rewind
                        return false;
                    }
                    break;
                }
                scanner->current_line_indent = indent;
            } else {
                // lone '/' at line start: not a comment — rewind so the
                // internal lexer can lex the expression continuation.
                return false;
            }
        }
        if (scanner->current_line_indent < current_indent) {
            scanner->stack_size--;
            lexer->result_symbol = DEDENT;
            return true;
        }
        // else: fall through — the re-measured line drives the
        // INDENT/NEWLINE logic below.
    }

    if (found_newline) {
        if (scanner->current_line_indent > current_indent && valid_symbols[INDENT]) {
            if (scanner->stack_size < 128) {
                scanner->indent_stack[scanner->stack_size++] = scanner->current_line_indent;
                lexer->mark_end(lexer);
                lexer->result_symbol = INDENT;
                return true;
            }
        }

        if (valid_symbols[NEWLINE]) {
            lexer->result_symbol = NEWLINE;
            return true;
        }
    } else {
        bool at_start_of_line = (start_column == 0 || start_column == indent);
        if (at_start_of_line) {
             if (scanner->current_line_indent > current_indent && valid_symbols[INDENT]) {
                if (scanner->stack_size < 128) {
                    scanner->indent_stack[scanner->stack_size++] = scanner->current_line_indent;
                    lexer->mark_end(lexer);
                    lexer->result_symbol = INDENT;
                    return true;
                }
            }
        }
    }

    return false;
}
