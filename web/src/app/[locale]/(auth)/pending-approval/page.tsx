import { useTranslations } from 'next-intl'

export default function PendingApprovalPage() {
  return (
    <div className="min-h-screen flex items-center justify-center bg-cream px-4">
      <div className="max-w-sm w-full text-center bg-white rounded-2xl p-8 shadow-sm border border-gray-100 space-y-3">
        <div className="text-5xl">⏳</div>
        <h2 className="font-serif text-xl text-gray-800">Chờ duyệt</h2>
        <p className="text-sm text-gray-500">
          Tài khoản của bạn đang chờ quản trị viên dòng họ phê duyệt. Vui lòng quay lại sau.
        </p>
      </div>
    </div>
  )
}
