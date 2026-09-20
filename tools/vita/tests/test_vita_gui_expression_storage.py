from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[3]
HEADER = (ROOT / "src/ui/Window.h").read_text(encoding="utf-8")
SOURCE = (ROOT / "src/ui/Window.cpp").read_text(encoding="utf-8")


def function(text: str, signature: str) -> str:
    start = text.index(signature)
    opening = text.index("{", start)
    depth = 1
    for pos in range(opening + 1, len(text)):
        depth += (text[pos] == "{") - (text[pos] == "}")
        if depth == 0:
            return text[start:pos + 1]
    raise AssertionError("unterminated function: " + signature)


class VitaGuiExpressionStorageTests(unittest.TestCase):
    def test_no_per_window_max_expression_array(self):
        self.assertNotIn("wexpOp_t ops[MAX_EXPRESSION_OPS]", HEADER)
        self.assertIn("idList<wexpOp_t *> expressionOpBlocks", HEADER)
        self.assertIn("EXPRESSION_OP_BLOCK_SIZE = 32", HEADER)
        self.assertIn("sizeof( idWindow ) < 8 * 1024", SOURCE)

    def test_append_keeps_returned_operation_addresses_stable(self):
        append = function(SOURCE, "wexpOp_t *idWindow::ExpressionOp()")
        self.assertIn("expressionOpBlocks.Append( NULL )", append)
        self.assertIn("new wexpOp_t[EXPRESSION_OP_BLOCK_SIZE]", append)
        self.assertIn("&expressionOpBlocks[blockIndex][slotIndex]", append)
        # A relocatable flat idList<wexpOp_t> would invalidate oop in the
        # recursive ternary parser; only the pointer table is allowed to grow.
        self.assertNotRegex(HEADER, r"idList\\s*<\\s*wexpOp_t\\s*>\\s+[A-Za-z_]\\w*\\s*;")
        self.assertNotRegex(append, r"\bops\.Append\b")

    def test_all_runtime_indexing_uses_accessor(self):
        self.assertNotRegex(SOURCE, r"\bops\s*\[")
        self.assertIn("op = ExpressionOpAt( i );", SOURCE)
        fixup = function(SOURCE, "void idWindow::FixupParms()")
        self.assertIn("wexpOp_t *op = ExpressionOpAt( i );", fixup)

    def test_storage_is_released_on_reinitialization(self):
        clear = function(SOURCE, "void idWindow::ClearExpressionOps()")
        self.assertIn("delete [] expressionOpBlocks[i]", clear)
        self.assertIn("expressionOpBlocks.Clear()", clear)
        self.assertIn("numOps = 0", clear)
        common = function(SOURCE, "void idWindow::CommonInit()")
        self.assertIn("ClearExpressionOps();", common)
        update = function(SOURCE, "bool idWindow::UpdateFromDictionary")
        self.assertIn("ClearExpressionOps();", update)

    def test_ternary_parser_still_retains_an_op_pointer(self):
        parse = function(SOURCE, "intptr_t idWindow::ParseExpressionPriority")
        self.assertIn("wexpOp_t *oop = NULL", parse)
        self.assertIn("oop->d = a", parse)
        # This is the exact reason the storage has to be address-stable while
        # ParseExpressionPriority recursively appends more operations.
        self.assertLess(parse.index("wexpOp_t *oop = NULL"), parse.index("oop->d = a"))


if __name__ == "__main__":
    unittest.main()
