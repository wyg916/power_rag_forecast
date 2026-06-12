import type { ThemeConfig } from 'antd';

export const themeTokens = {
  primary: '#00B894',
  primaryDark: '#008F72',
  primaryLight: '#E6F7F1',
  pageBg: '#F7F9FC',
  cardBg: '#FFFFFF',
  border: '#E5EAF0',
  title: '#1F2937',
  text: '#374151',
  secondary: '#6B7280',
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
    colorTextSecondary: themeTokens.secondary,
    colorBorder: themeTokens.border,
    colorBgLayout: themeTokens.pageBg,
    colorBgContainer: themeTokens.cardBg,
    borderRadius: 12,
    borderRadiusLG: 16,
    fontSize: 14,
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
      subMenuItemBg: 'transparent'
    },
    Card: {
      borderRadiusLG: 16,
      paddingLG: 20
    },
    Button: {
      borderRadius: 8,
      controlHeight: 36
    },
    Table: {
      headerBg: '#F8FAFC',
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
