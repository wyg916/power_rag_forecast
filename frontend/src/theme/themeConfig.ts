import type { ThemeConfig } from 'antd';

export const themeTokens = {
  primary: '#00B894',
  primaryDark: '#008F72',
  primaryHover: '#06C49F',
  primaryLight: '#E6F7F1',
  pageBg: '#F6F8FB',
  cardBg: '#FFFFFF',
  softBg: '#F8FAFC',
  border: '#E1E7F0',
  title: '#111827',
  text: '#334155',
  secondary: '#64748B',
  muted: '#94A3B8',
  danger: '#FF4D4F',
  warning: '#FAAD14',
  info: '#1677FF',
  purple: '#7C3AED'
};

export const themeConfig: ThemeConfig = {
  token: {
    colorPrimary: themeTokens.primary,
    colorSuccess: themeTokens.primary,
    colorWarning: themeTokens.warning,
    colorError: themeTokens.danger,
    colorInfo: themeTokens.info,
    colorText: themeTokens.title,
    colorTextBase: themeTokens.text,
    colorTextSecondary: themeTokens.secondary,
    colorTextTertiary: themeTokens.muted,
    colorBorder: themeTokens.border,
    colorBorderSecondary: '#E8EEF6',
    colorBgLayout: themeTokens.pageBg,
    colorBgContainer: themeTokens.cardBg,
    colorBgElevated: themeTokens.cardBg,
    borderRadius: 8,
    borderRadiusLG: 12,
    fontSize: 14,
    fontSizeSM: 13,
    fontSizeLG: 16,
    controlHeight: 36,
    controlHeightSM: 30,
    controlHeightLG: 40,
    fontFamily:
      '-apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC", "Microsoft YaHei", sans-serif'
  },
  components: {
    Layout: {
      bodyBg: themeTokens.pageBg,
      headerBg: themeTokens.cardBg,
      siderBg: themeTokens.cardBg
    },
    Menu: {
      itemSelectedBg: themeTokens.primaryLight,
      itemSelectedColor: themeTokens.primaryDark,
      itemHoverColor: themeTokens.primaryDark,
      itemBorderRadius: 10,
      itemHeight: 44,
      subMenuItemBg: 'transparent'
    },
    Card: {
      borderRadiusLG: 12,
      paddingLG: 16
    },
    Button: {
      borderRadius: 8,
      controlHeight: 36
    },
    Table: {
      headerBg: themeTokens.softBg,
      rowHoverBg: '#F0FFFA',
      borderColor: themeTokens.border
    },
    Tag: {
      borderRadiusSM: 8
    },
    Tabs: {
      itemSelectedColor: themeTokens.primaryDark,
      inkBarColor: themeTokens.primary
    }
  }
};
