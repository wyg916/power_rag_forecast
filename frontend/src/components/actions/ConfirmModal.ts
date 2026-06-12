import { Modal } from 'antd';
import type { ModalFuncProps } from 'antd';

export function ConfirmModal(props: ModalFuncProps) {
  return Modal.confirm({
    okText: '确认',
    cancelText: '取消',
    ...props
  });
}
