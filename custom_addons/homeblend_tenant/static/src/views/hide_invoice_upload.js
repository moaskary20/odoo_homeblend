import { patch } from "@web/core/utils/patch";
import { AccountMoveListController } from "@account/views/account_move_list/account_move_list_controller";
import { AccountMoveKanbanController } from "@account/views/account_move_kanban/account_move_kanban_controller";
import { FileUploadListRenderer } from "@account/views/file_upload_list/file_upload_list_renderer";
import { FileUploadKanbanRenderer } from "@account/views/file_upload_kanban/file_upload_kanban_renderer";

const CUSTOMER_MOVE_TYPES = ["out_invoice", "out_refund", "out_receipt"];

function isCustomerInvoiceContext(ctx = {}) {
    return CUSTOMER_MOVE_TYPES.includes(ctx.default_move_type);
}

patch(AccountMoveListController.prototype, {
    setup() {
        super.setup(...arguments);
        if (isCustomerInvoiceContext(this.props.context)) {
            this.showUploadButton = false;
        }
    },
});

patch(AccountMoveKanbanController.prototype, {
    setup() {
        super.setup(...arguments);
        if (isCustomerInvoiceContext(this.props.context)) {
            this.showUploadButton = false;
        }
    },
});

patch(FileUploadListRenderer.prototype, {
    onDragStart(ev) {
        if (isCustomerInvoiceContext(this.env.searchModel?.context)) {
            return;
        }
        super.onDragStart(ev);
    },
    onPaste(ev) {
        if (isCustomerInvoiceContext(this.env.searchModel?.context)) {
            return;
        }
        return super.onPaste(ev);
    },
});

patch(FileUploadKanbanRenderer.prototype, {
    onDragStart(ev) {
        if (isCustomerInvoiceContext(this.env.searchModel?.context)) {
            return;
        }
        super.onDragStart(ev);
    },
    onPaste(ev) {
        if (isCustomerInvoiceContext(this.env.searchModel?.context)) {
            return;
        }
        return super.onPaste(ev);
    },
});
