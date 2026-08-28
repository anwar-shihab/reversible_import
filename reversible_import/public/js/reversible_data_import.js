frappe.ui.form.on('Reversible Data Import', {
	refresh(frm) {
		frm.clear_custom_buttons();

		if (frm.doc.execution_status === 'Draft' || frm.doc.execution_status === 'Validated') {
			frm.add_custom_button(__('Preview'), () => {
				frm.call('preview').then((r) => {
					const data = r.message;
					frappe.msgprint({
						title: __('Import Preview'),
						message: __(
							'Total payloads: {0}<br>Total rows: {1}<br>Rollback support: {2}',
							[data.total_payloads, data.total_rows, data.rollback_support]
						),
						indicator: data.rollback_support === 'FULL' ? 'green' : 'orange',
					});
				});
			});
			frm.add_custom_button(__('Start Import'), () => {
				frm.call('start').then(() => frm.reload_doc());
			}, __('Actions'));
		}

		if (['Running', 'Queued', 'Stop Requested'].includes(frm.doc.execution_status)) {
			frm.add_custom_button(__('Cancel Import'), () => {
				frm.call('cancel').then(() => frm.reload_doc());
			}, __('Actions'));
		}

		if (
			['Success', 'Partial Success', 'Stopped'].includes(frm.doc.execution_status) &&
			['Not Requested', 'Complete'].includes(frm.doc.rollback_status)
		) {
			frm.add_custom_button(__('Rollback'), () => {
				frappe.confirm(
					__('This will delete all documents created by this import. Continue?'),
					() => frm.call('rollback').then(() => frm.reload_doc())
				);
			}, __('Actions'));
		}
	},
});
